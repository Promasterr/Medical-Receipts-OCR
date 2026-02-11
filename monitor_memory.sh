#!/bin/bash
# Monitor system memory usage and alert if approaching OOM

echo "=== System Memory Monitor ==="
echo "Press Ctrl+C to stop"
echo ""

while true; do
    clear
    echo "=== Memory Status - $(date '+%Y-%m-%d %H:%M:%S') ==="
    echo ""
    
    # Show memory usage
    free -h
    echo ""
    
    # Show vLLM process memory
    echo "vLLM Process Memory:"
    ps aux | grep -E "vllm.entrypoints" | grep -v grep | awk '{printf "  PID: %s | RAM: %s | CPU: %s%%\n", $2, $6/1024" MB", $3}'
    echo ""
    
    # Show Celery worker memory
    echo "Celery Workers Memory:"
    ps aux | grep -E "celery.*worker" | grep -v grep | awk '{sum+=$6} END {printf "  Total: %.0f MB across %d processes\n", sum/1024, NR}'
    echo ""
    
    # Calculate available memory percentage
    total=$(free | grep Mem | awk '{print $2}')
    available=$(free | grep Mem | awk '{print $7}')
    percent_available=$(awk "BEGIN {printf \"%.1f\", ($available/$total)*100}")
    
    echo "Available RAM: ${percent_available}%"
    
    # Alert if low
    if (( $(echo "$percent_available < 10" | bc -l) )); then
        echo "⚠️  WARNING: Less than 10% RAM available!"
    elif (( $(echo "$percent_available < 20" | bc -l) )); then
        echo "⚠️  CAUTION: Less than 20% RAM available"
    else
        echo "✓ Memory status: OK"
    fi
    
    echo ""
    echo "Checking for recent OOM kills..."
    recent_oom=$(dmesg | grep -i "out of memory" | tail -1)
    if [ -n "$recent_oom" ]; then
        echo "Last OOM event: $recent_oom"
    else
        echo "No recent OOM kills detected"
    fi
    
    sleep 5
done
