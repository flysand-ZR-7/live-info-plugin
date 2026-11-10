# Contributing to Live Information Plugin

Thank you for your interest in contributing to **Live Information Plugin**! We welcome community contributions to help make AI web intelligence secure, privacy-first, and accessible to everyone.

---

## 🛠️ Development Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/flysand-ZR-7/live-info-plugin.git
   cd live-info-plugin
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   pip install pytest pytest-asyncio respx
   ```

3. **Start local SearXNG (optional for live testing):**
   ```bash
   docker compose up -d
   ```

4. **Run the test suite:**
   ```bash
   pytest tests/ -v
   ```
   *Note: All unit tests run 100% offline using mocked network fixtures via `respx`.*

---

## 🛡️ Security Guidelines

Because this service bridges AI agents with the open web, security is paramount:
- **SSRF Prevention:** Any new endpoint that fetches external URLs must validate destination IPs via `app.security.validate_url_ssrf`.
- **Private IPs & Cloud Metadata:** All private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`) and cloud metadata services (`169.254.169.254`) must remain blocked.
- **Payload Limits:** Streaming requests must enforce size caps (default: 5MB) to prevent denial-of-service.

---

## 📋 Pull Request Process

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Write unit tests for any new functionality in `tests/`.
3. Verify all tests pass: `pytest tests/ -v`
4. Commit your changes with clear semantic commit messages:
   - `feat: add DuckDuckGo direct fallback backend`
   - `fix: resolve redirect timeout edge case`
   - `docs: update deployment instructions`
5. Push to your fork and submit a Pull Request to `main`.

---

## 📄 License

By contributing to this repository, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
