#!/bin/bash
#Nginx Service Management Script
ACTION=$1
if [ -z "$ACTION" ]; then
echo "Usage: $0 {start|stop|restart|status}"
exit 1
fi
case $ACTION in
start)
echo "Starting Nginx..."
systemctl start nginx
if systemctl is-active --quiet nginx; then
echo "Nginx started successfully"
else
echo "Failed to start Nginx"
fi
;;
stop)
echo "Stopping Nginx..."
systemctl stop nginx
echo "Nginx stopped"
;;
restart)
echo "Restarting Nginx..."
systemctl restart nginx
if systemctl is-active --quiet nginx; then
echo "Nginx restarted successfully" 
else
echo "Failed to restart nginx"
fi
;;
status)
systemctl status nginx
;;
*)
echo "Invalid action: $ACTION"
echo "usage: $0 {start|stop|restart|status}"
exit 1
;;
esac
