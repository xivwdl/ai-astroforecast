# AI Astroforecast

A daily astrology forecast based on astronomical calculations and written by AI. Each edition includes the forecast in RU and EN, the calculated facts, and a NASA photograph.

## Coolify

1. Connect this repository as a **Dockerfile** app. Expose port **8000** and use **/health** for the health check.
2. Add a volume at **/data**. Use a Docker volume. A bind mount must be writable by UID 10001.
3. Add **ZAI_API_KEY** as a runtime-only secret. Optionally set **ZAI_MODEL** (default `glm-4.7-flash`). Keep Coolify's built-in **SOURCE_COMMIT** enabled for the deployed source link.
4. Deploy, then add a scheduled task with command `python publish.py`, frequency `*/15 * * * *`, and timeout **300 seconds**. Use **Execute now** once. Connect your public domain after the first successful edition. An empty volume serves HTTP 503 until then.

The publisher checks for the next edition from 00:15 New York time (07:15 or 08:15 Moscow time). Positions use 12:00 Moscow time. Eclipse maxima are checked across the full Moscow calendar day. The previous edition stays live until both languages and a verified new image can be published together. When daily APOD is missing, a video, or lacks clear NASA-only attribution, the publisher uses a different Earth image from [NASA EPIC](https://epic.gsfc.nasa.gov/about). The image caption names its source and its own date.

## License

[GNU AGPL v3.0](LICENSE). Calculations use [pyswisseph 2.10.3.2](https://pypi.org/project/pyswisseph/2.10.3.2/#files) and [Swiss Ephemeris data](https://github.com/aloistr/swisseph/tree/6c9897279736b76e81f0b0039d05283a9ba59dc5/ephe) with their upstream license terms. NASA imagery is credited separately.
