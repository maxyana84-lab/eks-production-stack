#!/usr/bin/env python3
"""Checks the release graph of `helmfile build` output (Task 11.1).

    helmfile build | python3 scripts/check_helmfile.py
    helmfile -l 'name!=karpenter' build | python3 scripts/check_helmfile.py --skip karpenter   # offline use
"""
import argparse
import sys

import yaml

REQUIRED = {
    # release: namespace
    "kube-prometheus-stack": "monitoring",
    "external-secrets": "external-secrets",
    "external-dns": "external-dns",
    "karpenter": "karpenter",
    "database": "production",
    "backend": "production",
    "frontend": "production",
}
# (release, must come after): the order required by the exercise
ORDER = [("backend", "database"), ("frontend", "backend"), ("database", "external-secrets")]

parser = argparse.ArgumentParser()
parser.add_argument("--skip", action="append", default=[], help="release that is not part of the input")
args = parser.parse_args()

releases = {}
for doc in yaml.safe_load_all(sys.stdin):
    for r in (doc or {}).get("releases") or []:
        releases[r["name"]] = r

errors = []
for name, namespace in REQUIRED.items():
    if name in args.skip:
        continue
    if name not in releases:
        errors.append(f"missing release {name}")
    elif releases[name]["namespace"] != namespace:
        errors.append(f"{name}: namespace {releases[name]['namespace']} (expected {namespace})")

def short(ref):  # "namespace/name" -> "name"
    return ref.split("/")[-1]

for name, r in releases.items():
    for dep in r.get("needs") or []:
        if short(dep) not in releases and short(dep) not in args.skip:
            errors.append(f"{name} needs unknown release {dep}")

def depends_on(release, target, seen=()):
    """transitive: does `release` need `target`?"""
    for dep in releases.get(release, {}).get("needs") or []:
        d = short(dep)
        if d == target or (d not in seen and depends_on(d, target, seen + (release,))):
            return True
    return False

for release, after in ORDER:
    if release in releases and after in releases and not depends_on(release, after):
        errors.append(f"{release} must (transitively) need {after}")

# the infrastructure releases live in their own namespaces, never in "production"
for name in ("kube-prometheus-stack", "external-secrets", "external-dns", "karpenter"):
    if name in releases and releases[name]["namespace"] == "production":
        errors.append(f"{name} must not be in the production namespace")

print(f"{len(releases)} releases:", ", ".join(sorted(releases)))
if errors:
    print("\n".join("ERROR: " + e for e in errors))
    sys.exit(1)
print("release graph OK")
