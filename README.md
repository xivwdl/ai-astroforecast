# AI Astroforecast

A daily astrology forecast based on astronomical calculations and written by AI. Each edition includes the forecast in RU and EN, the calculated facts, and a NASA photograph.

## Coolify

1. Connect this repository as a **Dockerfile** app. Expose port **8000**. Leave the Coolify dashboard health check disabled to use the Dockerfile's built-in **/health** check.
2. Add a volume at **/data**. Use a Docker volume. A bind mount must be writable by UID 10001.
3. Add **ZAI_API_KEY** as a runtime-only secret. Optionally set **ZAI_MODEL** (default `glm-4.7-flash`). Keep Coolify's built-in **SOURCE_COMMIT** enabled for the deployed source link.
4. Deploy, then add a scheduled task with command `python publish.py`, frequency `*/15 * * * *`, and timeout **300 seconds**. Use **Execute now** once. Connect your public domain after the first successful edition. An empty volume serves HTTP 503 until then.

The publisher checks for the next edition from 00:15 New York time (07:15 or 08:15 Moscow time). Positions use 12:00 Moscow time. Eclipse maxima are checked across the full Moscow calendar day. The previous edition stays live until both languages and a verified new image can be published together. Photos come from NASA APOD. If today's APOD is a video, the publisher uses a recent APOD image different from the previous edition's. If the daily APOD is delayed, the previous edition stays live. The footer links to the original APOD post.

## Credits

Astrological consultation and interpretation review: **Kseniya Akhmitova**.

## License

[GNU AGPL v3.0](LICENSE). Calculations use [pyswisseph 2.10.3.2](https://pypi.org/project/pyswisseph/2.10.3.2/#files) and [Swiss Ephemeris data](https://github.com/aloistr/swisseph/tree/6c9897279736b76e81f0b0039d05283a9ba59dc5/ephe) with their upstream license terms. APOD images retain their original rights. See [NASA's APOD image-use guidance](https://science.nasa.gov/apod/apod-about/).
