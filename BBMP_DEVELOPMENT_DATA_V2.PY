import os
import csv
import re
import time
import logging
import requests
import urllib3
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import MergedCell
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed

START_YEAR = "2016-2017"
END_YEAR = "2026-2027"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://account.bbmpgov.in/PublicView/?l=1"
API_URL = "https://account.bbmpgov.in/PublicView/vss00CvStatusData.php"
OUTPUT_FOLDER = "BBMP_Development_Data"
MAX_WORKERS = 8
PAGE_SIZE = 100
REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(OUTPUT_FOLDER, "Scraping_Log.txt"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
session = requests.Session()
session.headers.update(HEADERS)
session.mount("https://", HTTPAdapter(max_retries=retry))
session.mount("http://", HTTPAdapter(max_retries=retry))
session.get(BASE_URL, verify=False)


def clean_html(text):
    if not text:
        return ""
    text = str(text).replace("<br/>", " ").replace("<br>", " ").replace("&nbsp;", " ")
    return " ".join(re.sub(r"<[^>]*>", "", text).split())


def extract_start_end_dates(jobcode_html):
    start_date, end_date = "", ""
    if not jobcode_html:
        return start_date, end_date
    match = re.search(r"Start\s*:\s*([0-9]{2}-[A-Za-z]{3}-[0-9]{4}).*?End\s*:\s*([0-9]{2}-[A-Za-z]{3}-[0-9]{4})", jobcode_html, re.IGNORECASE)
    if match:
        start_date = datetime.strptime(match.group(1), "%d-%b-%Y").strftime("%d/%m/%Y")
        end_date = datetime.strptime(match.group(2), "%d-%b-%Y").strftime("%d/%m/%Y")
    return start_date, end_date


def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def get_all_wards():
    print("\nLoading ward list...")
    response = session.get(API_URL, params={"pAction": "LoadCombo", "pTableName": "vssmasters.vss20toward"}, timeout=REQUEST_TIMEOUT, verify=False)
    ward_list = []
    
    for ward in response.json():
        ward_id = str(ward.get("rid", "")).strip()
        ward_name = clean_html(ward.get("rname", "")).strip()
        
        m = re.match(r"^(?:oo|o)?(\d{3})\s+(.*)", ward_name, re.IGNORECASE)
        if m and 1 <= int(m.group(1)) <= 255:
            gen = "current" if ward_name.startswith(m.group(1)) else ("old" if ward_name.lower().startswith("oo") else "intermediate")
            ward_list.append({"id": ward_id, "number": int(m.group(1)), "generation": gen, "name": ward_name})

    ward_list.sort(key=lambda x: (x["generation"], x["number"]))
    return ward_list


def get_financial_years():
    print("\nLoading financial years...")
    response = session.get(API_URL, params={"pAction": "LoadFinancialYear", "pTableName": "vss.vss00tvfinancialyear"}, timeout=REQUEST_TIMEOUT, verify=False)
    financial_years = []
    for year in response.json():
        if year.get("rid") == "-1":
            continue
        start = datetime.strptime(year["datefrom"], "%Y-%m-%d")
        end = start.replace(year=start.year + 1) - timedelta(days=1)
        financial_years.append({"id": year["rid"], "name": year["rname"], "date_from": start.strftime("%d-%b-%Y"), "date_to": end.strftime("%d-%b-%Y")})
    return financial_years


def get_parent_records(ward_id, ward_name, financial_years):
    print(f"\nProcessing Ward : {ward_name}")
    parent_records, seen_wbids = [], set()
    
    for fy in financial_years:
        page, last_wbids = 0, None
        while True:
            params = {
                "pAction": "LoadPaymentGridData", "pCriteria": "", "pDateFrom": fy["date_from"], "pDateTo": fy["date_to"],
                "pDateType": "pDT", "pOrderBy": "1", "pFinancialYearID": -1, "pBudgetHeadID": "-1", "pDDOIDs": "",
                "pWardIDs": "", "pDateFilterYN": "true", "pWardID": ward_id, "filterscount": "0", "groupscount": "0",
                "pagenum": str(page), "pagesize": str(PAGE_SIZE), "recordstartindex": str(page * PAGE_SIZE), "recordendindex": str((page + 1) * PAGE_SIZE)
            }
            try:
                data = session.get(API_URL, params=params, timeout=REQUEST_TIMEOUT, verify=False).json()
                if not isinstance(data, list) or not data:
                    break
                current_wbids = tuple(row.get("wbid", "") for row in data)
                if current_wbids == last_wbids:
                    break
                last_wbids = current_wbids
            except Exception:
                break

            for row in data:
                wbid = row.get("wbid")
                if wbid and (fy["id"], wbid) not in seen_wbids:
                    seen_wbids.add((fy["id"], wbid))
                    row["Financial_Year"] = fy["name"]
                    row["Ward_ID"] = ward_id
                    parent_records.append(row)

            if len(data) < PAGE_SIZE:
                break
            page += 1
            time.sleep(0.20)
            
    return parent_records


def fetch_complete_row_data(parent_record, ward_id):
    wbid = parent_record.get("wbid")
    if not wbid:
        return []

    start_date, end_date = extract_start_end_dates(parent_record.get("jobcode", ""))
    meta, approvals = {}, []

    try:
        meta = session.get(API_URL, params={"pAction": "LoadWorksbillDetails", "pWorkBillID": str(wbid)}, timeout=REQUEST_TIMEOUT, verify=False).json()
    except Exception:
        pass

    try:
        approvals = session.get(API_URL, params={"pAction": "LoadGridApprovalLevels", "pWorkBillID": str(wbid), "filterscount": "0", "groupscount": "0", "pagenum": "0", "pagesize": "50", "recordstartindex": "0", "recordendindex": "50"}, timeout=REQUEST_TIMEOUT, verify=False).json()
    except Exception:
        pass

    mobile = meta.get("contractormobile1") or meta.get("contractormobile") or meta.get("mobile") or ""
    base_row = {
        "Ward_Query_ID/RID": ward_id, "Start_Date": start_date, "End_Date": end_date,
        "Mobile": clean_html(mobile), "Ward_Generation": parent_record.get("rname", ""),
        "Financial_Year": parent_record.get("Financial_Year", ""), "Main_Serial_No": parent_record.get("slno", ""),
        "Work_Code_Name": parent_record.get("wcname", ""), "Work_Bill_ID": wbid,
        "Name_of_Work": clean_html(parent_record.get("nameofwork", "")), "Total_Amount": parent_record.get("amount", ""),
        "Budget_Head": clean_html(meta.get("budget", "")), "Division": clean_html(meta.get("ddoname", "")),
        "Contractor_Name": clean_html(meta.get("contractorname", "")), "Bill_Type": clean_html(meta.get("billtype", "")),
        "Gross_Amount": clean_html(meta.get("gross", "")), "Deductions": clean_html(meta.get("deduction", "")),
        "Net_Amount": clean_html(meta.get("nett", "")), "Current_Level": clean_html(meta.get("approvallevel", ""))
    }

    if isinstance(approvals, list) and approvals:
        rows = []
        for item in approvals:
            r = base_row.copy()
            r.update({
                "Detail_Row_ID": item.get("id", ""), "Approval_Stage_Name": clean_html(item.get("name", "")),
                "Milestone_Date": clean_html(item.get("date", "")), "Approval_Remarks": clean_html(item.get("remarks", ""))
            })
            rows.append(r)
        return rows

    fallback = base_row.copy()
    fallback.update({"Detail_Row_ID": "", "Approval_Stage_Name": "", "Milestone_Date": "", "Approval_Remarks": ""})
    return [fallback]


def process_ward(ward, financial_years):
    ward_id, ward_name = ward["id"], ward["name"]
    try:
        parent_records = get_parent_records(ward_id, ward_name, financial_years)
        if not parent_records:
            return None

        output_rows = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(fetch_complete_row_data, r, ward_id) for r in parent_records]
            for future in as_completed(futures):
                try:
                    if rows := future.result():
                        output_rows.extend(rows)
                except Exception:
                    pass

        try:
            output_rows.sort(key=lambda r: (-int(r.get("Financial_Year", "0").split("-")[0]), int(r.get("Main_Serial_No", 0)) if str(r.get("Main_Serial_No", "")).isdigit() else 999999))
        except Exception:
            pass

        serial_counter, seen_wbis = 0, {}
        for row in output_rows:
            wbid = row.get("Work_Bill_ID")
            if wbid not in seen_wbis:
                serial_counter += 1
                seen_wbis[wbid] = serial_counter
            row["Main_Serial_No"] = str(seen_wbis[wbid])

        xlsx_path = os.path.join(OUTPUT_FOLDER, safe_filename(ward_name.replace(" ", "_")) + ".xlsx")
        fieldnames = [
            "Ward_Query_ID/RID", "Financial_Year", "Start_Date", "End_Date", "Main_Serial_No", "Work_Code_Name",
            "Work_Bill_ID", "Name_of_Work", "Total_Amount", "Budget_Head", "Division", "Contractor_Name", "Mobile",
            "Bill_Type", "Gross_Amount", "Deductions", "Net_Amount", "Current_Level", "Detail_Row_ID",
            "Approval_Stage_Name", "Milestone_Date", "Approval_Remarks"
        ]

        wb = Workbook()
        ws = wb.active
        ws.title = "Development Data"
        ws.freeze_panes = "A2"
        ws.append(fieldnames)
        ws.row_dimensions[1].height = 28

        for row in output_rows:
            ws.append([row.get(col, "") for col in fieldnames])

        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = Font(bold=True, size=11)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for col in ws.columns:
            try:
                ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(len(str(c.value or "")) for c in col) + 2, 50)
            except Exception:
                pass

        header_map = {cell.value: cell.column for cell in ws[1]}
        for col_name in ["Total_Amount", "Gross_Amount", "Deductions", "Net_Amount"]:
            if col := header_map.get(col_name):
                for r in range(2, ws.max_row + 1):
                    cell = ws.cell(row=r, column=col)
                    try:
                        cell.value = float(cell.value)
                        cell.number_format = '#,##0.00'
                    except Exception:
                        pass

        merge_cols = ["Start_Date", "End_Date", "Main_Serial_No", "Work_Code_Name", "Work_Bill_ID", "Name_of_Work", "Total_Amount", "Budget_Head", "Division", "Contractor_Name", "Mobile", "Bill_Type", "Gross_Amount", "Deductions", "Net_Amount", "Current_Level"]
        try:
            start_row = 2
            while start_row <= ws.max_row:
                serial = ws.cell(row=start_row, column=header_map.get("Main_Serial_No", 1)).value
                fy = ws.cell(row=start_row, column=header_map.get("Financial_Year", 2)).value
                end_row = start_row
                while end_row + 1 <= ws.max_row and ws.cell(row=end_row + 1, column=header_map.get("Main_Serial_No", 1)).value == serial and ws.cell(row=end_row + 1, column=header_map.get("Financial_Year", 2)).value == fy:
                    end_row += 1
                if end_row > start_row:
                    for cn in merge_cols:
                        if c := header_map.get(cn):
                            try:
                                ws.merge_cells(start_row=start_row, start_column=c, end_row=end_row, end_column=c)
                            except Exception:
                                pass
                start_row = end_row + 1
        except Exception:
            pass

        border = Border(left=Side(style="thin", color="000000"), right=Side(style="thin", color="000000"), top=Side(style="thin", color="000000"), bottom=Side(style="thin", color="000000"))
        for row in ws.iter_rows():
            for cell in row:
                if not isinstance(cell, MergedCell):
                    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = border

        wb.save(xlsx_path)
        return {"Ward": ward_name, "Parent": len(parent_records), "Rows": len(output_rows), "Status": "Success"}
    except Exception as e:
        return {"Ward": ward_name, "Parent": 0, "Rows": 0, "Status": f"Failed: {e}"}


def main():
    start_time = time.time()
    wards, financial_years, summary, total_rows, total_parent = get_all_wards(), get_financial_years(), [], 0, 0

    for idx, ward in enumerate(wards, start=1):
        print(f"\n[{idx}/{len(wards)}] Processing: {ward['name']}")
        result = process_ward(ward, financial_years)
        if result:
            summary.append(result)
            total_rows += result["Rows"]
            total_parent += result["Parent"]
        else:
            summary.append({"Ward": ward["name"], "Parent": 0, "Rows": 0, "Status": "No Data"})
        time.sleep(0.5)

    with open(os.path.join(OUTPUT_FOLDER, "Summary.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Ward", "Parent", "Rows", "Status"])
        writer.writeheader()
        writer.writerows(summary)

    print(f"\nDone! Time Taken: {(time.time() - start_time)/60:.2f} minutes. Saved in {OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()