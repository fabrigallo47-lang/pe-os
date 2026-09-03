# Extraction test rig on a GPU server

Runs all three PDF models plus the side-by-side test UI on one box, so
they can be compared at GPU speed instead of the CPU speeds that made the
local comparison unrepresentative.

| model | what it is | local CPU speed |
|---|---|---|
| Granite-Docling-258M | 258M VLM, reads the page image, emits DocTags | ~50-60 s/page |
| Docling classic | PP layout model + TableFormer | ~7 s/page |
| PaddleOCR-VL | PP-DocLayoutV3 + 0.9B VLM | ~12 s/page |

Those numbers are CPU-bound and are the reason for this deployment; all
three should be seconds or less on a GPU.

## Before you start: this changes a stated invariant

`CLAUDE.md` invariant 7 says nothing leaves this machine except the
operations listed in `vault/policy/policy-table.md`. Sending real deal
documents to a rented GPU is a deliberate reversal of that, not a
deployment detail. **Add a policy-table row recording it** — what leaves,
to which provider, under what retention — before the first real document
is uploaded. The system is built so that a human can always answer "who
saw this evidence"; an undocumented egress path breaks that answer.

Nothing here enforces that for you. It is a one-line row and it is the
difference between a considered decision and an accident.

## Instance

- **GPU**: any 16GB+ card (A10G, L4, RTX 4090, A100). The largest model is
  0.9B, so this is about throughput, not capacity.
- **Disk**: 60GB+ — ~15GB image, ~4GB weights, plus room for uploads.
- **RAM**: 16GB+. Locally, a 0.9B model in float32 drove macOS to grow a
  10GB swapfile; give it real headroom.
- **CUDA**: image is built on 12.6. Match the host driver or change the
  base image tag.

## Run

```bash
export PE_OS_UI_TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
export SITE_ADDRESS=extract.yourdomain.com     # must resolve to this host
echo "token: $PE_OS_UI_TOKEN"                  # you need it to log in

cd deploy && docker compose up -d --build
```

First start downloads ~4GB of weights into the `models` volume; later
starts reuse them. Then open:

```
https://extract.yourdomain.com/?token=<PE_OS_UI_TOKEN>
```

The token is stored in an HttpOnly cookie on first load, so it appears in
the URL once rather than in every request.

### Optional: chart-to-table

```bash
PE_OS_PADDLE_CHARTS=1 docker compose up -d
```

Off by default on purpose. PaddleOCR-VL can convert a chart to a table,
but those numbers are **inferred from pixels, not read from text**. PAN-100
found this produces "structurally confident but factually wrong" values on
a real waterfall/EBITDA-bridge chart. When enabled, output is prefixed
`[chart-recognition, MODEL-DERIVED not read text]` so it cannot be
mistaken for extracted text. Treat it as a proposal for human
confirmation — never bind it to a question as evidence. Under invariant 3
it cannot be `derived` anyway: "a model looked at pixels" is not an
inspectable derivation.

## Security

The UI is a dev/QA tool that accepts file uploads and returns their
contents. With real deal documents that makes it a confidentiality
surface, so:

- **It refuses to bind anything but loopback without `PE_OS_UI_TOKEN`.**
  This is enforced in `tools/extraction_test_ui.py::main`, not a
  convention.
- **The app container publishes only to host loopback.** The Caddy proxy
  is the only thing with a public port, and it terminates TLS with an
  automatic Let's Encrypt certificate. Without it, uploads and extracted
  text cross the network in cleartext.
- **Uploads are held in a temp dir for the life of the process** and
  removed on clean exit. `docker compose down` discards them. They are
  *not* removed if the container is hard-killed.
- Restrict the security group to your own IP if the provider allows it.
  The token is a shared secret, not a user model — anyone holding it has
  full access.

## What it does not do

- No authentication beyond one shared token; no user accounts, no audit
  log of who uploaded what.
- No encryption at rest. Uploaded documents sit unencrypted on the
  instance disk while being processed.
- Not hardened for untrusted uploads — it is a test rig for documents you
  already trust.

If real deal data will live here for more than a session, those three
gaps deserve closing first.
