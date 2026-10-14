# Legacy SimpliSafe doorbell streaming — implementation plan

Status: research verified; adapter **not yet implemented**. Keep this work on `feature/doorbell-support`; do not change the five working LiveKit sessions.

## Evidence

The Homebridge SimpliSafe implementation at `homebridge-simplisafe3/homebridge-simplisafe3`, `src/accessories/camera.js`, selects `legacy` when `cameraSettings.admin.webRTCProvider` is absent or `simplisafe`; it selects `livekit` for `mist`.

Its `src/lib/streamingDelegate.js` uses the camera UUID and authenticated requests to:
- `https://media.simplisafe.com/v1/{camera_uuid}/flv?x={width}&audioEncoding=AAC` for video;
- `https://media.simplisafe.com/v1/{camera_uuid}/mjpg?x={width}&fr=1` for a snapshot.

It supplies `Authorization: Bearer <access_token>` and feeds the FLV input into FFmpeg. Its `src/simplisafe.js` also calls `POST /v1/ss3/subscriptions/{subscription_id}/camera-wakeup` with `{ "wakeAll": true }` before streaming. This is a reference implementation, not a guarantee that the user's doorbell supports the same endpoint in 2026.

Home Assistant's camera integration accepts a URL from `async def stream_source(self) -> str | None` for FFmpeg/HLS streaming. The source must be readable by the stream worker; plain authenticated headers are not represented by a simple URL.

## Proposed adapter and security boundaries

1. Handle **only** provider `simplisafe` in the new legacy path. Do not alter `mist` or `kvs` WebRTC provider processing.
2. Build a local, streaming proxy that uses the authenticated SimpliSafe session to retrieve FLV. Authenticate and authorize requests from HA's stream worker; keep the camera access token server-side, never in URL/query parameters, dashboard YAML, events, diagnostics, or logs.
3. Bridge the proxy to Home Assistant's stream integration via `stream_source()`, or identify an officially supported HA stream input accepting authentication headers directly. Ensure FFmpeg can demux FLV and generate HLS; verify audio compatibility.
4. Bound buffers, enforce connection timeouts and cancellation, and release upstream connections when viewers disconnect. Consider concurrency and token refresh.
5. Test the standalone doorbell path on the development branch, verifying actual moving frames and recoverability after reconnect. Only merge into `main` when working.

## Avoid

- Logging bearer tokens, FLV payloads or signed URLs.
- Inserting access tokens into `stream_source()` URLs.
- Returning the legacy FLV endpoint as a bare source; it requires authenticated access.
- Changing the working LiveKit `Host` fix.
- Treating a snapshot or an enabled Play button as confirmed live video.

## References

- https://github.com/homebridge-simplisafe3/homebridge-simplisafe3/blob/master/src/accessories/camera.js
- https://github.com/homebridge-simplisafe3/homebridge-simplisafe3/blob/master/src/lib/streamingDelegate.js
- https://developers.home-assistant.io/docs/core/entity/camera/
