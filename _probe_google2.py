"""Extract Google careers job listings from AF_initData blobs."""

from __future__ import annotations

import json
import re
import urllib.request

SEARCH = (
    "https://www.google.com/about/careers/applications/jobs/results"
    "?q=Software%20Engineering%20Intern"
    "&location=United%20States"
)

req = urllib.request.Request(
    SEARCH,
    headers={"User-Agent": "Mozilla/5.0 (compatible; InternshipIntel/0.1)"},
)
html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")

# AF_initDataCallback({key: 'ds:1', ... data:...});
blobs = re.findall(
    r"AF_initDataCallback\((\{.*?}\)\);",
    html,
    flags=re.S,
)
print("blobs", len(blobs))

# Find job cards via ssk attributes
cards = re.findall(
    r"ssk='(\d+):(\d+)'[^>]*>.*?Software Engineering Intern[^<]{0,120}",
    html,
    flags=re.S,
)
print("card matches", len(cards), cards[:5])

# Simpler: href job urls
hrefs = re.findall(
    r'href="(/about/careers/applications/jobs/results/\d+-[^"]+)"',
    html,
)
print("hrefs", len(hrefs))
for h in hrefs[:15]:
    print(" ", h)

# Titles near intern
titles = re.findall(
    r"(Software Engineering Intern[^\"<,]{0,60})",
    html,
)
print("titles unique", sorted(set(titles))[:20])

# Location strings
locs = re.findall(r"(Mountain View, CA, USA[^\"\\]{0,40})", html)
print("locs", locs[:5])
