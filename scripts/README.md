# Scripts Directory

This directory contains utility and maintenance scripts for the Unilever Image Study application.

## 📁 Available Scripts

### 1. `auto_abandon_inprogress.py`
**Purpose**: Automatically marks in-progress study responses as abandoned after 10 minutes of inactivity.

**Usage**:
```bash
cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy
source venv/bin/activate
python3 scripts/auto_abandon_inprogress.py
```

**Cron Setup** (runs every 5 minutes):
```bash
*/5 * * * * cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy && source venv/bin/activate && python3 scripts/auto_abandon_inprogress.py >> logs/auto_abandon.log 2>&1
```

**What it does**:
- Finds responses that are in-progress but have no activity for >10 minutes
- Marks them as abandoned using the `mark_abandoned()` method
- Updates study counters (decrements in_progress, increments abandoned)
- Logs all actions

**Status**: ✅ Fixed - No longer has double-decrement bug

---

### 2. `cleanup_completed_studies.py`
**Purpose**: Performs two cleanup tasks:
1. Deletes panelist task data for completed studies to free up database space
2. Marks all in-progress responses as abandoned

**Usage**:
```bash
cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy
source venv/bin/activate
python3 scripts/cleanup_completed_studies.py
```

**Cron Setup** (runs daily at 2 AM):
```bash
0 2 * * * cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy && source venv/bin/activate && python3 scripts/cleanup_completed_studies.py >> logs/cleanup.log 2>&1
```

**What it does**:
- Part 1: Deletes `StudyPanelistTasks` for studies with `status='completed'`
- Part 2: Marks all in-progress responses as abandoned
- Adds cleanup timestamp to completed studies
- Logs deletion counts and actions

**Status**: ✅ Fixed - Now uses `mark_abandoned()` method consistently

---

### 3. `run_cleanup.sh`
**Purpose**: Shell wrapper script for running cleanup operations.

**Usage**:
```bash
./scripts/run_cleanup.sh
```

**What it does**:
- Changes to project directory
- Activates virtual environment
- Runs the cleanup script
- Logs execution to `logs/cleanup.log`

**Status**: ✅ Ready to use

---

### 4. `migrate_ref_ids_to_string.py`
**Purpose**: Database migration script to convert reference IDs to string format.

**Usage**: Run once for database migration (already completed if database is set up)
```bash
cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy
source venv/bin/activate
python3 scripts/migrate_ref_ids_to_string.py
```

---

## 🚀 Quick Start

### Set Up Cron Jobs (One-Time Setup)

1. **Edit crontab**:
   ```bash
   crontab -e
   ```

2. **Add these lines**:
   ```bash
   # Auto-abandon inactive responses every 5 minutes
   */5 * * * * cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy && source venv/bin/activate && python3 scripts/auto_abandon_inprogress.py >> logs/auto_abandon.log 2>&1

   # Clean up completed studies daily at 2 AM
   0 2 * * * cd /Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy && source venv/bin/activate && python3 scripts/cleanup_completed_studies.py >> logs/cleanup.log 2>&1
   ```

3. **Save and exit** (ESC, then `:wq` in vim)

4. **Verify**:
   ```bash
   crontab -l
   ```

### Monitor Logs

```bash
# View auto-abandon logs
tail -f logs/auto_abandon.log

# View cleanup logs
tail -f logs/cleanup.log
```

## 📚 Documentation

For detailed information, see:
- **CRON_SETUP.md** - Complete cron job setup guide
- **AUDIT_REPORT.md** - Technical details on count update logic
- **COUNT_AUDIT_SUMMARY.md** - Summary of audit findings and fixes

## ✅ All Scripts Audited

All scripts have been audited for correct count updates and data consistency. Key fixes applied:
- ✅ Fixed double-decrement bug in `auto_abandon_inprogress.py`
- ✅ Updated `cleanup_completed_studies.py` to use `mark_abandoned()` method
- ✅ Ensured all count updates use actual list lengths
- ✅ Added proper safety checks and logging

## 🔧 Troubleshooting

### Script not running?
1. Check Python environment is activated
2. Verify MongoDB is running
3. Check file permissions
4. Review log files for errors

### Cron job not working?
1. Verify cron service is running
2. Check absolute paths are correct
3. Ensure logs directory exists
4. Test script manually first

### Database errors?
1. Verify MongoDB connection in `config.py`
2. Check MongoDB is accessible
3. Ensure all required models are imported

## 🤝 Contributing

When adding new scripts:
1. Follow existing patterns for count updates
2. Use model methods (`mark_abandoned()`, `mark_completed()`) instead of manual flag setting
3. Always use `len(list)` for count calculations, not stored count fields
4. Include proper error handling and logging
5. Add documentation to this README
6. Test manually before adding to cron

## 📞 Support

For issues or questions:
1. Check the documentation files
2. Review log files in `logs/` directory
3. Test scripts manually to see detailed error messages
4. Check MongoDB connection and data

