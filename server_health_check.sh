#!/bin/bash
# =================================================
# Server Health Check Script
# Linux Capstone Project 2
# =================================================
LOGFILE="/var/log/health_check.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
PASS=0
FAIL=0
log() {
echo "[$TIMESTAMP]$1" | tee -a $LOGFILE
}
check_service() {
SERVICE=$1
if systemctl is-active --quiet $SERVICE; then
log " PASS: $SERVICE is running"
((PASS++))
else
log " FAIL: $SERVICE is NOT running"
((FAIL++))
# Attempt to restart
systemctl restart $SERVICE
log " Attempted restart of $SERVICE"
fi
}
check_port() {
PORT=$1
NAME=$2
if ss -tlnp | grep -q ":$PORT"; then
log " PASS: Port $PORT ($NAME) is open"
((PASS++))
else
log " FAIL: Port $PORT ($NAME) is NOT open"
((FAIL++))
fi
}
check_disk() {
THRESHOLD=80
USAGE=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
if [ $USAGE -lt $THRESHOLD ]; then
log " PASS: Disk usage is ${USAGE}% (below ${THRESHOLD}% threshold)"
((PASS++))
else
log "WARN: Disk usage is ${USAGE}% (above ${THRESHOLD}% threshold)"
((FAIL++))
fi
}
check_memory() {
FREE_MEM=$(free |awk 'NR==2{printf "%.0f", $4/$2*100}')
if [ $FREE_MEM -gt 10 ]; then
log " PASS : Free memory is ${FREE_MEM}%"
((PASS++))
else
log " WARN: Low memory --- only ${FREE_MEM}% free"
((FAIL++))
fi
}
check_http() {
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/)
if [ "$HTTP_CODE" == "200"]; then
log "PASS:HTTP response code is $HTTP_CODE"
((PASS++))
else
log "FAIL: HTTP response code is $HTTP_CODE (expected 200)"
((FAIL++))
fi
}
# ---Run All Checks---
log "============================================="
log "Server Health Check started"
log "=============================================" 
check_service "nginx"
check_service "firewalld"
check_port 80 "HTTP"
check_port 22 "SSH"
check_disk
check_memory
check_http
log "=============================================" 
log "Health Check Complete: PASS=$PASS | FAIL=$FAIL"
log "=============================================" 
echo ""
