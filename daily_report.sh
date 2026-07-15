#!/bin/bash
REPORT_FILE="/var/log/daily_report_$(date +%Y%m%d).txt"
echo "================================================" > $REPORT_FILE
echo "Daily System Report - $(date)" >> $REPORT_FILE
echo "================================================" > $REPORT_FILE

echo "" >> $REPORT_FILE
echo "--- System Info ---" >> $REPORT_FILE
hostname >> $REPORT_FILE
uptime >> $REPORT_FILE
echo "" >> $REPORT_FILE
echo "--- Disk Usage ---" >> $REPORT_FILE
df -h >> $REPORT_FILE
echo "" >> $REPORT_FILE
echo "--- Memory usage ---" >> $REPORT_FILE
free -h >> $REPORT_FILE
echo "" >> $REPORT_FILE
echo "--- Top 5 CPU Process ---" >> $REPORT_FILE
ps aux --sort=-%cpu | head -6 >> $REPORT_FILE
echo "" >> $REPORT_FILE
echo "--- Logged In Users ---" >> $REPORT_FILE
who >> $REPORT_FILE
echo "" >> $REPORT_FILE
echo "--- Recent Error Logs ---" >> $REPORT_FILE
tail -20 /var/log/messages 2>/dev/null || tail -20 /var/log/syslog 2>/dev/null >> $REPORT_FILE
echo "Report saved to: $REPORT_FILE"
