import json
import sys
import urllib.request

commit_sha = sys.argv[1] if len(sys.argv) > 1 else "dbd8b43"
url = f"https://api.github.com/repos/zayanahmed23/guard-rail-edge/commits/{commit_sha}/check-runs"
req = urllib.request.Request(url, headers={"User-Agent": "CI-Checker", "Accept": "application/vnd.github.v3+json"})

try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print(f"Total check runs: {data['total_count']}")
        all_completed = True
        all_success = True
        for cr in data["check_runs"]:
            name = cr["name"]
            status = cr["status"]
            conclusion = cr["conclusion"]
            print(f"  {name}: {status} - {conclusion}")
            if status != "completed":
                all_completed = False
            if conclusion != "success":
                all_success = False
        if data["total_count"] > 0 and all_completed and all_success:
            print("ALL_GREEN")
        elif not all_completed:
            print("PENDING")
        else:
            print("SOME_FAILED")
except Exception as e:
    print(f"Error checking CI: {e}")

