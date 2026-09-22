# Pico local manager

This supplements, but does not replace, the Mac voice server or the ASR/TTS on 95.

## Components

- Web: production Vue bundle + Nginx, host 8002.
- API: Java 21 built from this checkout; only accessible on the Compose network.
- MySQL 8.4 and Redis 7.4: dedicated persistent volumes, no host ports.
- Credentials: `.runtime/manager.env`, mode 0600, ignored by Git and Docker build context.
- Initial host bind: 127.0.0.1. Administrator-only authentication; public registration is permanently disabled.

Use the repository root as the working directory. Build the frontend in `main/manager-web` before starting the stack. The configuration is `deploy/local/compose.yaml`, with `--env-file .runtime/manager.env`. The API image is built from local modified source, not an unmodified upstream prebuilt image.

`import_models.py` reads the current local voice configuration, validates all three providers, and defaults to a dry run. `--apply` imports the model credentials directly to MySQL without printing them, sets model defaults and updates templates for new agents. It does not change existing agents or activate manager mode in the voice service. The API restart discards its in-process cache; perform the import before using the manager UI.

Before enabling manager mode: verify API health, model records, authorization and the complete server-base response. Back up `main/pico-server/data/.config.yaml`. Register/bind a device and verify agent-models before claiming the conversation chain works. The cloud OTA forwarding currently requires review when switching from Python-only OTA to the manager's activation/OTA service.

## Firmware center

The logged-in navigation contains **固件中心**. Currently supports FoloToy AI Passport / ESP32-C3 / 8MB only. It accepts `pico-firmware.json` plus the exact `.bin` segments, validates SHA-256, matches chip family, and requires explicit board/backup confirmation. No arbitrary address input or whole-chip erase is offered. Written regions are checked via MD5 by esptool-js.

Firmware packages are exported by `pico-esp32/scripts/export_pico_firmware.py` from the matching IDF build. Addresses come from `flasher_args.json`; board identity comes from generated `sdkconfig.json`. No compiled firmware is bundled until a real build passes.

Use Chrome/Edge at localhost or HTTPS for Web Serial. A browser cannot reliably infer the physical board wiring from the ESP chip ID. The user must confirm the board. SHA-256 verifies package integrity, not publisher authenticity. Only use trusted Pico builds. First-time USB flashing, Wi-Fi provisioning and device binding are distinct steps; USB Wi-Fi provisioning is not implemented.

## Security/acceptance boundaries

Do not expose the manager, database or build actions to the public reverse proxy. The inherited frontend dependencies have audit findings; keep the manager local pending remediation. Do not use `npm audit fix --force` to downgrade flyio or upgrade the Vue stack blindly.

Container restart policies require Docker Desktop to be running. This is not proof of start-at-login after a Mac reboot. No physical USB write is performed by deployment scripts.


## Administrator-only authentication (2026-09-21)

Public registration, SMS and public password recovery are disabled in the backend and removed from the login UI. Legacy registration/recovery routes redirect to login. Only active super-administrators can receive tokens; the authentication realm rejects existing ordinary-user tokens on every protected request. Device/service-secret authentication is unchanged.

On a fresh database, set `PICO_ADMIN_USERNAME` and a strong `PICO_ADMIN_PASSWORD` (16+ characters) in the private environment file for the first startup. The application uses the existing password-strength/BCrypt service to create the first administrator. If accounts exist but no active administrator remains, startup fails instead of promoting a user or resetting passwords. Existing administrators are never modified by bootstrap variables.

After successful provisioning, remove the bootstrap variables and recreate the API container. This deployment has done so. The initial credentials are stored in `.runtime/admin-access.txt` with mode 0600; this file is not an active configuration file and will be stale after a password change. Administrator password changes still use the authenticated account settings. Keep the manager private until the cloud HTTPS/access-control work is finished.

Verification: 13 targeted Java tests passed (login restrictions, existing-token restrictions, bootstrap safety); frontend 19 contract tests passed; real encrypted administrator login and user-info read passed, and the smoke-test token was expired afterwards. Registration/SMS/recovery returned disabled errors in runtime checks.
