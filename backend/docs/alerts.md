# GridSense Alert System

## Overview

The alert system generates actionable notifications for users based on energy usage analysis, ML model predictions, and scheduled summaries.

## Alert Types

### 1. Post-Import Alerts
Triggered automatically after successful NEM12 upload:
- **Anomaly Alerts**: Daily spikes, overnight usage, unusual patterns
- **High-Priority Recommendations**: Immediate actions to reduce costs

### 2. ML Training Completion
Notifies users when personalized ML models finish training:
- **Success**: "Your personalized forecast models are ready"
- **Insufficient Data**: "We need more data to create personalized forecasts"

### 3. High Bill Forecasts
Daily checks at 6pm UTC:
- Alerts if projected monthly bill exceeds $300
- Alerts if on track for >20% increase vs. average (after 7 days)

### 4. Weekly Summaries
Sent every Sunday at 8am UTC:
- Total kWh for the past 7 days
- Average daily consumption
- Estimated cost
- Comparison to previous weeks (future)

## Architecture

### Services
- **AlertService** (`app/services/alert_service.py`):
  - Orchestrates alert generation
  - Handles deduplication via stable event keys
  - Respects user notification preferences
  
- **NotificationService** (`app/services/notification_service.py`):
  - Manages push token registration
  - Sends notifications via Expo Push API
  - Tracks delivery status

### Background Tasks
- **publish_after_import**: Checks anomalies + recommendations after upload
- **check_all_forecasts_task**: Daily bill forecast check for all meters
- **send_weekly_summaries_task**: Weekly energy summary for all meters
- **train_meter_models_task**: Extended to notify on completion

### Scheduler
- **Automation rules**: Every minute (unchanged)
- **ML retraining**: Sunday 3am UTC weekly
- **Weekly summaries**: Sunday 8am UTC (after retraining)
- **Forecast checks**: Daily 6pm UTC

## Deduplication

Each alert includes a `dedupe_key` in its metadata to prevent duplicate notifications:

```python
dedupe_key = f"{meter_id}:{alert_type}:{date_or_id}"
```

Examples:
- Anomaly: `"123:anomaly:daily_spike:2026-08-15"`
- Recommendation: `"123:recommendation:peak_shift_001"`
- Forecast: `"123:forecast:2026-08"`
- Training: `"123:training:true:forecast_anomaly"`
- Weekly: `"123:weekly:2026-08-11"`

The system checks the last 100 notifications for each type before sending.

## User Preferences

Users can control alert delivery via notification preferences:
- `anomaly_alerts`: Enable/disable anomaly detection alerts
- `forecast_updates`: ML training and bill forecast alerts
- `recommendations`: High-priority recommendation alerts
- `weekly_summary`: Weekly energy summary emails/push
- `peak_alerts`: Real-time peak usage warnings (future)
- `savings_tips`: Monthly savings tip notifications

Managed via:
- `GET /api/v1/notifications/preferences`
- `PUT /api/v1/notifications/preferences`

## Testing

### Manual Testing
```bash
# Trigger post-import alerts
POST /api/v1/upload (upload NEM12 file)

# Check weekly summary generation
python -m app.tasks send_weekly_summaries_task

# Check forecast alerts
python -m app.tasks check_all_forecasts_task

# View notification history
GET /api/v1/notifications/list
```

### Automated Testing
- Unit tests: `tests/test_alert_service.py` (to be added)
- Integration tests: `tests/test_notifications.py` (existing)

## Future Enhancements

1. **Smart Deduplication**: Only alert if anomaly severity increases
2. **Personalized Thresholds**: Learn user-specific alert preferences
3. **Actionable Alerts**: Deep-link to specific recommendations or devices
4. **Alert History**: Track which alerts led to user action
5. **Email Digest**: Alternative to push notifications for web users
6. **Cost Comparison**: Compare alerts to previous periods for trend detection
