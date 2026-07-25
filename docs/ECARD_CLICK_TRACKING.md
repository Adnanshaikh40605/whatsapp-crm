# E-Card / E-Brochure Click Tracking — Handoff

Track **which customer** clicked **E-Brochure**, and **when**.

Meta does **not** send URL-button click webhooks.  
WhatsFlow uses a **unique short link per send** → logs the click → redirects to the real e-card.

---

## Architecture

```
Staff clicks green "E-Card" on CRM Inquiry
        ↓
Pest CRM → WhatsFlow SSO + send template (track_ecard=true)
        ↓
WhatsFlow creates token, sends WhatsApp with button URL:
  https://api.driveronhire.ai/r/<TOKEN>
        ↓
Customer taps E-Brochure
        ↓
GET /r/<TOKEN>/  → save phone + datetime → redirect to pestcontrol99.com/e-card/
        ↓
Pest CRM "E-Card Tracking" page lists clicks
```

**One Meta template** (not one per client). Dynamic URL ends with `{{1}}`.

---

## WhatsFlow developer (this repo) — DONE / TODO

### Implemented

| Item | Detail |
|------|--------|
| Redirect | `GET https://api.driveronhire.ai/r/<token>/` |
| Send with tracking | `POST /api/inbox/messages/template/` + `track_ecard: true` |
| List clicks | `GET /api/inbox/ecard-tracking/` |
| List / create links | `GET|POST /api/inbox/ecard-links/` |
| Models | `ECardTrackedLink`, `ECardClick` |
| Template command | `python manage.py setup_pest_ecard_tracked "Pest Control"` |

### Deploy checklist

1. Push backend + run migration `0007_ecard_tracking`
2. Set Railway env (optional): `PUBLIC_BASE_URL=https://api.driveronhire.ai`
3. Submit tracked template to Meta and wait for **APPROVED**:
   ```bash
   python manage.py setup_pest_ecard_tracked "Pest Control"
   ```
4. Sync templates in WhatsFlow UI
5. Test click without WhatsApp:
   - SSO → `POST /api/inbox/ecard-links/` with phone  
   - Open `tracking_url` in browser  
   - `GET /api/inbox/ecard-tracking/` should show the phone + time

### New template (required for real WhatsApp sends)

| Field | Value |
|-------|--------|
| Name | `pest_ecard_tracked` |
| Language | `en_US` |
| Call Now | `+918080748282` (static) |
| E-Brochure URL | `https://api.driveronhire.ai/r/{{1}}` (dynamic) |

Current `pest_business_details` has a **static** URL → cannot pass per-client suffix. Use `pest_ecard_tracked` after Meta approves it.

---

## Pest Control CRM developer — implement this

### 1) Env (already)

```env
VITE_WHATSAPP_API_KEY=wf_...
VITE_WHATSFLOW_API_URL=https://api.driveronhire.ai/api
VITE_WHATSFLOW_ORG_ID=96d71345-5c98-4e9a-8095-0eae9ff855c4
```

### 2) Green **E-Card** button on Inquiries

After SSO, send:

```http
POST https://api.driveronhire.ai/api/inbox/messages/template/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "phone": "919869108406",
  "template_name": "pest_ecard_tracked",
  "language": "en_US",
  "track_ecard": true,
  "customer_name": "Sanjay Khair",
  "external_id": "765",
  "ecard_destination_url": "https://www.pestcontrol99.com/e-card/",
  "body_params": []
}
```

| Field | Meaning |
|-------|---------|
| `track_ecard` | Creates unique token + attaches to E-Brochure button |
| `external_id` | Inquiry ID (shows on tracking page) |
| `customer_name` | Display name |
| `ecard_destination_url` | Final page after click (default e-card site) |

Until `pest_ecard_tracked` is **APPROVED**, keep using current send without `track_ecard` (no per-click identity).

### 3) Page: **E-Card Tracking** (sidebar already exists)

Load clicks:

```http
GET https://api.driveronhire.ai/api/inbox/ecard-tracking/?limit=200
Authorization: Bearer <access_token>
```

Response example:

```json
{
  "success": true,
  "data": {
    "total_clicks": 12,
    "unique_phones": 8,
    "results": [
      {
        "phone": "919869108406",
        "customer_name": "Sanjay Khair",
        "external_id": "765",
        "clicked_at": "2026-07-25T15:00:00Z",
        "destination_url": "https://www.pestcontrol99.com/e-card/",
        "template_name": "pest_ecard_tracked"
      }
    ]
  }
}
```

**UI table columns:** Phone · Customer · Inquiry ID · Clicked at · Template  

Optional filters: `?phone=9869` or `?external_id=765`

### 4) Test today (before Meta approval)

```javascript
// 1) SSO login (same as now)
// 2) Create test link
const link = await fetch(`${API}/inbox/ecard-links/`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    phone: '919372792693',
    customer_name: 'Adnan Shaikh',
    external_id: 'TEST-1',
  }),
}).then(r => r.json())

// 3) Open link.data.tracking_url in browser (simulates E-Brochure tap)
// 4) Refresh E-Card Tracking page → see phone + time
```

---

## What to tell each developer (copy/paste)

### To WhatsFlow developer

> Deploy e-card tracking: migration `0007_ecard_tracking`, public route `/r/<token>/`, embed APIs `ecard-tracking` + `ecard-links`, `track_ecard` on template send.  
> Run `setup_pest_ecard_tracked` and wait for Meta approval of `pest_ecard_tracked` (URL `https://api.driveronhire.ai/r/{{1}}`).

### To Pest Control CRM developer

> On Inquiry **E-Card** send, call template API with `track_ecard: true`, `template_name: "pest_ecard_tracked"`, `customer_name`, `external_id` (inquiry id).  
> Build **E-Card Tracking** page from `GET /api/inbox/ecard-tracking/` — show phone, name, inquiry id, clicked_at.  
> You can test tracking today via `POST /api/inbox/ecard-links/` + opening `tracking_url` (no WhatsApp needed).

---

*July 2026 — Pest Control 99 / WhatsFlow*
