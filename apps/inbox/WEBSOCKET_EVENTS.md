# WhatsFlow Inbox WebSocket Events

Real-time inbox updates are delivered over WebSocket so CRM clients do **not** need to poll `GET /api/inbox/conversations/`.

## Connection

| Client | URL |
|--------|-----|
| WhatsFlow app | `wss://<api-host>/ws/inbox/<org_id>/?token=<access_jwt>` |
| Embed CRM | `wss://<api-host>/ws/inbox/?token=<access_jwt>` |

Auth: valid JWT access token (SSO login or WhatsFlow login).

### Heartbeat

Client → server:

```json
{ "type": "ping" }
```

Server → client:

```json
{ "type": "pong" }
```

Recommended client interval: **30 seconds**.

### Connection ack

On successful connect:

```json
{ "type": "connected", "org_id": "<uuid>" }
```

---

## Event pipeline

```
Meta Webhook → Save Message → Redis (Channels) → WebSocket Broadcast → CRM UI
```

Broadcasts are fired **immediately** after the database write in the same request/task — there is no polling delay.

`GET /api/inbox/conversations/` is only for:

- Initial page load
- Pagination
- Search / filters
- Manual refresh

---

## Server → client events

All payloads include a `type` field. `conversation_updated` also includes `event` (same value) for embed clients.

### `new_message`

Inbound message saved from Meta webhook.

```json
{
  "type": "new_message",
  "message": {
    "id": "uuid",
    "conversation_id": "uuid",
    "conversation": "uuid",
    "direction": "inbound",
    "message_type": "text",
    "content": "Hello",
    "status": "delivered",
    "created_at": "2026-06-25T10:00:00Z",
    "whatsapp_message_id": "wamid.xxx"
  }
}
```

### `message_created`

Same `message` object as above. Used by the WhatsFlow main app when any message is created (inbound or outbound).

### `message_sent`

Outbound message queued or confirmed sent.

- **On send (API):** fired immediately when the message row is created (optimistic UI).
- **On Meta webhook `sent`:** fired when delivery status advances (unless already sent optimistically from the send task).

```json
{
  "type": "message_sent",
  "message": { "...": "full message object" }
}
```

### `message_delivered`

Meta delivery receipt applied.

```json
{
  "type": "message_delivered",
  "message": {
    "id": "uuid",
    "conversation_id": "uuid",
    "status": "delivered",
    "whatsapp_message_id": "wamid.xxx",
    "sent_at": "...",
    "delivered_at": "...",
    "read_at": null,
    "failed_at": null,
    "error_reason": null
  },
  "conversation": {
    "id": "uuid",
    "last_outbound_status": "delivered"
  }
}
```

### `message_read`

Meta read receipt applied. Same shape as `message_delivered` with `status: "read"`.

### `message_status_updated`

Canonical status event (WhatsFlow main app). Always sent with delivery status changes.

```json
{
  "type": "message_status_updated",
  "message": {
    "id": "uuid",
    "conversation_id": "uuid",
    "status": "delivered",
    "whatsapp_message_id": "wamid.xxx",
    "sent_at": "...",
    "delivered_at": "...",
    "read_at": null,
    "failed_at": null,
    "error_reason": null
  },
  "conversation": {
    "id": "uuid",
    "last_outbound_status": "delivered"
  }
}
```

Embed clients may also receive `message_sent` / `message_delivered` / `message_read` with the same payload and a different `type`.

### `conversation_updated`

Patch a **single** conversation in the list — do not refetch the full list.

Sent when:

- New inbound message
- New outbound message
- Unread count changes (e.g. mark read)
- Last message preview / timestamp changes
- Outbound delivery status changes

```json
{
  "type": "conversation_updated",
  "event": "conversation_updated",
  "conversation_id": "uuid",
  "last_message": "Hello",
  "unread_count": 2,
  "updated_at": "2026-06-25T10:00:00Z",
  "last_message_at": "2026-06-25T10:00:00Z",
  "conversation": {
    "id": "uuid",
    "last_message_preview": "Hello",
    "last_message_at": "2026-06-25T10:00:00Z",
    "unread_count": 2,
    "last_outbound_status": "delivered",
    "metadata": { "last_message_direction": "inbound" },
    "updated_at": "2026-06-25T10:00:00Z"
  }
}
```

**CRM usage:** find `conversation_id` in local state and merge `last_message`, `unread_count`, `updated_at`, `last_message_at`.

---

## Client → server events

Relayed to all connections in the same organization (excluding sender echo is not implemented — all clients receive the event).

### `typing`

```json
{
  "type": "typing",
  "conversation_id": "uuid",
  "user_id": "uuid",
  "is_typing": true
}
```

### `presence`

```json
{
  "type": "presence",
  "user_id": "uuid",
  "status": "online"
}
```

---

## Infrastructure

| Layer | Technology |
|-------|------------|
| Pub/sub | Redis via `channels_redis` |
| WebSocket | Django Channels (`InboxConsumer`, `EmbedInboxConsumer`) |
| Group name | `inbox_<organization_id>` |
| Cleanup | `group_discard` on disconnect |
| Heartbeat | Client `ping` / server `pong` |

Duplicate prevention:

- Inbound webhooks skip duplicate `whatsapp_message_id`
- Status updates ignore out-of-order/downgrade events (`should_apply_status`)
- Celery send task does not re-emit `message_sent` embed alias (already sent on queue)

---

## Recommended CRM handlers

```typescript
switch (event.type) {
  case 'new_message':
  case 'message_sent':
    appendOrUpdateMessage(event.message)
    break
  case 'message_delivered':
  case 'message_read':
  case 'message_status_updated':
    updateMessageStatus(event.message)
    break
  case 'conversation_updated':
    patchConversationList({
      id: event.conversation_id,
      last_message: event.last_message,
      unread_count: event.unread_count,
      last_message_time: event.last_message_at,
    })
    break
  case 'typing':
    showTypingIndicator(event.conversation_id)
    break
  case 'presence':
    updateAgentPresence(event)
    break
}
```

Do **not** call `GET /api/inbox/conversations/` on every message — rely on `conversation_updated` and message events instead.
