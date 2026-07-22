"""Probe Google careers job page for scrapeable structure."""

from __future__ import annotations

import re
import urllib.request

URL = (
    "https://www.google.com/about/careers/applications/jobs/results/"
    "85564713261245126-software-engineering-intern-bs-summer-2027"
)
SEARCH = (
    "https://www.google.com/about/careers/applications/jobs/results"
    "?q=Software%20Engineering%20Intern%20Summer%202027"
    "&location=United%20States"
)

for label, u in [("job", URL), ("search", SEARCH)]:
    req = urllib.request.Request(
        u,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; InternshipIntel/0.1)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")
    print("===", label, "len", len(html))
    print("title present", "Software Engineering Intern" in html)
    print("summer 2027", "Summer 2027" in html)
    print("job id", "85564713261245126" in html)
    print("JobPosting", "JobPosting" in html)
    print("ld+json", "application/ld+json" in html)
    for key in ("__NEXT_DATA__", "AF_initDataCallback", "WIZ_global_data", "jobs"):
        print(key, key in html)
    # Extract visible-ish title snippets
    m = re.search(r"Software Engineering Intern[^<]{0,80}", html)
    print("snippet", m.group(0) if m else None)
    # Any JSON blobs with the job id
    for m in re.finditer(r".{0,40}85564713261245126.{0,80}", html):
        print("ctx", m.group(0)[:120])
        break
