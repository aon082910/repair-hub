# Repair-Hub

A self-hosted repair reference and shop manager. Keep vehicles, repair guides with photos, wiring diagrams, a trouble-code lookup, and customers, work orders and invoices in one place. It runs offline on your own hardware.

It starts as a blank system you fill in yourself. The only content included is about 140 generic OBD-II trouble codes. It doesn't copy anyone's paid service data, though you can save a link to your own ALLDATA subscription on a vehicle page.

Handy bits:

- **Vehicle pages** with tabs for guides, diagrams, and live NHTSA recalls and complaints.
- **Free guide search** through iFixit's open guides.
- **Shop tools** for customers, work orders and invoices, with scheduled backups built in.

Image: [allornothing/repair-hub](https://hub.docker.com/r/allornothing/repair-hub) · Source: [aon082910/repair-hub](https://github.com/aon082910/repair-hub)

## Install

**Unraid:** search **Repair-Hub** in Apps, or add the template from [AoN-Unraid-Apps](https://github.com/aon082910/AoN-Unraid-Apps).

**Docker:**

```bash
docker run -d --name repair-hub -p 8080:8000 \
  -e PUID=99 -e PGID=100 -e TZ=Etc/UTC \
  -e DJANGO_SECRET_KEY="$(openssl rand -hex 32)" \
  -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_PASSWORD=change-me \
  -v /mnt/user/appdata/repair-hub:/config \
  allornothing/repair-hub:latest
```

Open `http://<server>:8080/` and log in with that superuser.

| Setting | Default | What it's for |
|---|---|---|
| Port | `8080` → `8000` | Web UI |
| `/config` | `/mnt/user/appdata/repair-hub` | Database and uploads. Back this folder up and you've backed up everything |
| `DJANGO_SECRET_KEY` | none | Signs sessions |
| `DJANGO_SUPERUSER_*` | `admin` | First admin account |
| `BACKUP_INTERVAL_HOURS` | `24` | Automatic backups, keeping `BACKUP_RETENTION_COUNT` (14) |

If you see a `Bad Request (400)` page, add the address in your browser to `DJANGO_ALLOWED_HOSTS`.

## Help

[Open an issue](https://github.com/aon082910/repair-hub/issues).
