# Cross-Device WiFi Connectivity Test

## Server Status
✅ Flask server running on `0.0.0.0:5000`
- Local Access: http://127.0.0.1:5000
- Network Access: http://10.35.176.59:5000

## CORS Configuration
✅ Flask-CORS enabled for `/api/*` endpoints with wildcard origins

## Network Diagnostics Endpoint
Test connectivity: **GET /api/network-status**

### From Local Device (10.35.176.59):
```bash
curl http://127.0.0.1:5000/api/network-status
```

### From Remote Device (different WiFi IP):
```bash
curl http://10.35.176.59:5000/api/network-status
```

## Expected Response:
```json
{
  "status": "online",
  "server": {
    "hostname": "DESKTOP-XXX",
    "ip": "10.35.176.59",
    "port": 5000,
    "urls": {
      "local": "http://127.0.0.1:5000",
      "network": "http://10.35.176.59:5000"
    }
  },
  "client": {
    "ip": "10.35.176.XX",
    "user_agent": "..."
  },
  "same_network": true,
  "timestamp": "2026-04-30T11:XX:XXX"
}
```

## Testing Checklist

### Phase 1: Network Connectivity
- [ ] Test /api/network-status from local browser
- [ ] Test /api/network-status from remote device on same WiFi
- [ ] Verify response includes client IP and "same_network" flag
- [ ] Verify CORS headers present (Access-Control-Allow-Origin: *)

### Phase 2: Authentication
- [ ] Sign up new user from remote device
- [ ] Login from remote device
- [ ] Verify session works across requests

### Phase 3: Constellation Chat
- [ ] Open constellation from Device 1 (server)
- [ ] Add Device 2 user as friend from Device 1
- [ ] Open constellation from Device 2 (remote)
- [ ] Send message from Device 1 → check appears on Device 2 within 1.5s
- [ ] Send message from Device 2 → check appears on Device 1 within 1.5s
- [ ] Verify graph visualization renders on both devices

### Phase 4: Ideas Mode
- [ ] Open ideas mode from Device 1
- [ ] Send idea from Device 1 → verify on Device 2
- [ ] Send idea from Device 2 → verify on Device 1
- [ ] Verify idea graph updates in real-time

### Phase 5: All Features
- [ ] Test friend requests cross-device
- [ ] Test profile updates cross-device
- [ ] Test image uploads cross-device
- [ ] Verify all API endpoints accessible from remote IP

## Troubleshooting

**Issue: Remote device cannot reach server (connection timeout)**
- Check firewall: Allow port 5000
- Check server is binding to 0.0.0.0 (not just localhost)
- Verify devices on same WiFi network
- Test connectivity: `ping 10.35.176.59` from remote device

**Issue: CORS errors in browser console**
- Check Flask-CORS import and initialization
- Verify CORS(app) called in create_app
- Check /api/network-status returns correct headers

**Issue: Messages not syncing between devices**
- Check database is persistent (SQLAlchemy models in use)
- Verify both devices fetching from same database
- Check message polling still runs (1.5s intervals)
- Review browser console for fetch errors

**Issue: Remote device shows blank constellation page**
- Check /api/constellation/get_chat returns data
- Verify auth tokens/session working remotely
- Check JavaScript console for errors
- Test /api/network-status to confirm network connectivity

## Commands to Test

```bash
# Test from remote device
curl http://10.35.176.59:5000/api/network-status

# Check CORS headers
curl -i http://10.35.176.59:5000/api/network-status

# Test message API from remote (after login)
curl http://10.35.176.59:5000/api/constellation/messages/1

# Verify server logs show remote requests
# (Watch Flask server terminal for requests from remote IP)
```

## Key Infrastructure Pieces
1. **Server**: Flask app on 0.0.0.0:5000
2. **CORS**: Wildcard enabled for /api/* routes
3. **Database**: SQLAlchemy models persist messages
4. **Polling**: Frontend fetches every 1.5 seconds
5. **Paths**: All API calls use relative paths (/api/...)

---

Last Updated: 2026-04-30
Status: Ready for cross-device testing
