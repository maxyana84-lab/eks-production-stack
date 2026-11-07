#!/usr/bin/env python3
"""Prints the S3 lifecycle configuration for the backup bucket.

The retention (30 / 60 / 90 days) is read from charts/database/values.yaml (backup.retention),
so the chart and the bucket cannot drift apart.
"""
import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
backup = yaml.safe_load((ROOT / "charts/database/values.yaml").read_text())["backup"]
retention = backup["retention"]
assert retention["standardIaDays"] >= 30, "S3 requires at least 30 days before STANDARD_IA"
assert retention["standardIaDays"] < retention["glacierDays"] < retention["expireDays"]

print(json.dumps({
    "Rules": [{
        "ID": "backup-tiering-and-expiry",
        "Status": "Enabled",
        "Filter": {"Prefix": backup["prefix"] + "/"},
        "Transitions": [
            {"Days": retention["standardIaDays"], "StorageClass": "STANDARD_IA"},
            {"Days": retention["glacierDays"], "StorageClass": "GLACIER"},
        ],
        "Expiration": {"Days": retention["expireDays"]},
        # the bucket is versioned: old versions disappear at the same time
        "NoncurrentVersionExpiration": {"NoncurrentDays": retention["expireDays"]},
        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
    }]
}, indent=2))
