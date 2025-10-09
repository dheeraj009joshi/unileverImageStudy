# Cron Job Setup Guide

This guide explains how to set up automated maintenance tasks (cron jobs) for the Unilever Image Study application.

## Available Cron Scripts

### 1. Auto-Abandon In-Progress Responses
**Script**: `scripts/auto_abandon_inprogress.py`
**Purpose**: Automatically marks in-progress responses as abandoned if there's no activity for more than 10 minutes.
**Frequency**: Run every 5 minutes

### 2. Cleanup Completed Studies
**Script**: `scripts/cleanup_completed_studies.py`
**Purpose**: 
- Deletes panelist task data for completed studies to free up database space
- Marks all in-progress responses as abandoned

**Frequency**: Run daily (recommended) or weekly

## Setting Up Cron Jobs

### Method 1: Using the Shell Script (Recommended)

1. **Make the shell script executable** (already done):
   ```bash
   chmod +x scripts/run_cleanup.sh
   ```

2. **Edit your crontab**:
   ```bash
   crontab -e
   ```

3. **Add the following cron job entries**:

   ```bash
   # Auto-abandon in-progress responses every 5 minutes
   */5 * * * * cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy && source venv/bin/activate && python3 scripts/auto_abandon_inprogress.py >> logs/auto_abandon.log 2>&1

   # Cleanup completed studies daily at 2:00 AM
   0 2 * * * cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy && source venv/bin/activate && python3 scripts/cleanup_completed_studies.py >> logs/cleanup.log 2>&1
   ```

4. **Save and exit** (in vi/vim: press `ESC`, then type `:wq` and press `ENTER`)

### Method 2: Manual Cron Setup

If you prefer more control, you can set up each script individually:

```bash
# Open crontab editor
crontab -e

# Add these lines (adjust paths as needed):

# Auto-abandon stale responses every 5 minutes
*/5 * * * * /usr/bin/env python3 /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy/scripts/auto_abandon_inprogress.py >> /var/log/auto_abandon.log 2>&1

# Cleanup completed studies daily at 2 AM
0 2 * * * /usr/bin/env python3 /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy/scripts/cleanup_completed_studies.py >> /var/log/cleanup.log 2>&1
```

## Cron Schedule Syntax

```
* * * * * command
│ │ │ │ │
│ │ │ │ └─── Day of week (0-7, Sunday = 0 or 7)
│ │ │ └───── Month (1-12)
│ │ └─────── Day of month (1-31)
│ └───────── Hour (0-23)
└─────────── Minute (0-59)
```

### Common Examples:
- `*/5 * * * *` - Every 5 minutes
- `0 * * * *` - Every hour
- `0 2 * * *` - Every day at 2:00 AM
- `0 0 * * 0` - Every Sunday at midnight
- `0 0 1 * *` - First day of every month at midnight

## Verifying Cron Jobs

### Check if cron jobs are installed:
```bash
crontab -l
```

### View log files:
```bash
# Auto-abandon logs
tail -f logs/auto_abandon.log

# Cleanup logs
tail -f logs/cleanup.log
```

### Test scripts manually:
```bash
# Test auto-abandon script
cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy
source venv/bin/activate
python3 scripts/auto_abandon_inprogress.py

# Test cleanup script
python3 scripts/cleanup_completed_studies.py
```

## What Each Script Does

### `auto_abandon_inprogress.py`

**Triggers when**:
- Response has `is_in_progress = True`
- Response has `is_abandoned = False`
- Response has `is_completed = False`
- `last_activity` is more than 10 minutes ago

**Actions**:
1. Marks response as abandoned using `response.mark_abandoned()` method
2. Updates study counters:
   - Decrements `in_progress_responses`
   - Increments `abandoned_responses`
3. Sets abandonment timestamp and reason
4. Logs the action

**Benefits**:
- Frees up study slots for new participants
- Provides accurate analytics on abandonment rates
- Prevents participants from holding slots indefinitely

### `cleanup_completed_studies.py`

**Part 1: Delete Panelist Tasks**

**Triggers when**:
- Study has `status = 'completed'`

**Actions**:
1. Finds all `StudyPanelistTasks` for the completed study
2. Deletes all panelist task documents
3. Adds `cleanup_timestamp` to the study
4. Logs deletion count

**Benefits**:
- Frees up database space (panelist tasks can be large)
- Maintains completed response data for analytics
- Keeps database performant

**Part 2: Mark In-Progress as Abandoned**

**Triggers when**:
- Any response has `is_in_progress = True`
- Response is not completed or abandoned

**Actions**:
1. Marks all in-progress responses as abandoned using `mark_abandoned()` method
2. Updates study counters properly
3. Sets abandonment timestamp and reason
4. Logs the action

**Benefits**:
- Cleans up stale in-progress responses
- Provides accurate response statistics
- Prevents data inconsistencies

## Troubleshooting

### Cron job not running?

1. **Check cron service is running**:
   ```bash
   # macOS
   sudo launchctl list | grep cron
   
   # Linux
   sudo systemctl status cron
   ```

2. **Check cron logs**:
   ```bash
   # macOS
   tail -f /var/log/system.log | grep cron
   
   # Linux
   tail -f /var/log/syslog | grep CRON
   ```

3. **Verify file permissions**:
   ```bash
   ls -l scripts/auto_abandon_inprogress.py
   ls -l scripts/cleanup_completed_studies.py
   ls -l scripts/run_cleanup.sh
   ```

4. **Test script manually** to see error messages:
   ```bash
   cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy
   source venv/bin/activate
   python3 scripts/auto_abandon_inprogress.py
   ```

### No logs being created?

1. **Create logs directory** if it doesn't exist:
   ```bash
   mkdir -p /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy/logs
   ```

2. **Check directory permissions**:
   ```bash
   ls -ld logs/
   ```

### Database connection errors?

1. **Check MongoDB is running**:
   ```bash
   # If using Docker
   docker ps | grep mongo
   
   # If using local MongoDB
   brew services list | grep mongodb
   ```

2. **Verify config.py** has correct MongoDB connection string

3. **Test database connection** manually:
   ```bash
   cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy
   source venv/bin/activate
   python3 -c "from mongoengine import connect; from config import config; connect(host=config['development']().MONGODB_SETTINGS['host']); print('✅ Database connection successful')"
   ```

## Monitoring

### Set up email notifications (optional)

You can configure cron to email you when jobs complete or fail:

```bash
# Add at the top of your crontab
MAILTO=your-email@example.com

# Then add your cron jobs below
*/5 * * * * cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy && source venv/bin/activate && python3 scripts/auto_abandon_inprogress.py
```

### Monitor with a dashboard

Consider using a monitoring tool like:
- **Cronitor** (https://cronitor.io/)
- **Healthchecks.io** (https://healthchecks.io/)
- **Sentry Crons** (https://sentry.io/for/cron-monitoring/)

## Best Practices

1. **Always redirect output** to log files with `>> logs/script.log 2>&1`
2. **Use absolute paths** in cron jobs
3. **Test scripts manually** before adding to cron
4. **Monitor log files** regularly to catch errors
5. **Rotate log files** to prevent them from growing too large
6. **Set appropriate frequencies** based on your application needs
7. **Document any changes** to cron schedules

## Log Rotation (Optional)

To prevent log files from growing too large, set up log rotation:

Create `/etc/logrotate.d/unilever-study`:

```
/Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 dheeraj staff
}
```

## Removing Cron Jobs

To remove cron jobs:

```bash
# Edit crontab
crontab -e

# Delete the lines you want to remove, then save and exit

# Or remove all cron jobs:
crontab -r
```

## Support

For issues or questions, refer to:
- **Audit Report**: `AUDIT_REPORT.md` - Details on count update logic
- **Application Logs**: `logs/` directory
- **Database**: Check MongoDB collections directly if needed

## Change Log

- **2025-10-09**: Initial cron job setup with audit and fixes
  - Fixed double-decrement bug in `auto_abandon_inprogress.py`
  - Updated `cleanup_completed_studies.py` to use `mark_abandoned()` method
  - Created comprehensive documentation

