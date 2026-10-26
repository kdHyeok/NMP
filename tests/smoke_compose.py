"""Explicit Docker smoke: dummy secrets, isolated network, disposable volume/project.

Run after `docker build --target runtime -t nmp:local .`:
    python -m tests.smoke_compose
"""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(args, *, check=True, **kwargs):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60, check=check, **kwargs)


def main():
    suffix = uuid.uuid4().hex[:12]
    project, volume = "nmp-test-" + suffix, "nmp-config-test-" + suffix
    image = run(["docker", "image", "inspect", "nmp:local", "--format", "{{.Id}}"]).stdout.strip()
    rendered = json.loads(run(["docker", "compose", "-f", "compose.yaml", "config", "--format", "json"]).stdout)
    service = rendered["services"]["nmp"]
    service.pop("build", None)
    service.pop("networks", None)
    service.update(image=image, user="10001:10001", network_mode="none")
    service["volumes"] = [{"type": "volume", "source": "fixture", "target": "/run/nmp", "read_only": True}]
    service["environment"]["CONTROL_PLANE_BASE_URL"] = "http://127.0.0.1:1"
    service["healthcheck"].update(interval="1s", start_period="1s")
    rendered.pop("networks", None)
    rendered["volumes"] = {"fixture": {"external": True, "name": volume}}
    run(["docker", "volume", "create", volume])
    with tempfile.TemporaryDirectory() as temporary:
        file = Path(temporary) / "compose.json"
        file.write_text(json.dumps(rendered), encoding="utf-8")
        compose = ["docker", "compose", "-p", project, "-f", str(file)]
        try:
            seed = "from pathlib import Path; from naver_mail_mcp.config import save_config; save_config(Path('/run/nmp'), {'email':'offline@naver.com','password':'dummy-mail-password','name':'','mode':'server','tunnel_id':'tunnel_'+'0'*32,'tunnel_key':'dummy-runtime-key'})"
            run(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "128", "--mount", f"type=volume,src={volume},dst=/run/nmp", image, "python", "-B", "-c", seed])
            run(compose + ["config", "--quiet"])
            run(compose + ["up", "-d", "--no-build"])
            container = run(compose + ["ps", "-q"]).stdout.strip()
            assert container
            def inspect():
                return json.loads(run(["docker", "inspect", container]).stdout)[0]
            state = inspect()
            assert state["Config"]["User"] == "10001:10001"
            assert state["HostConfig"]["ReadonlyRootfs"]
            assert state["HostConfig"]["NetworkMode"] == "none"
            assert not state["HostConfig"]["PortBindings"]
            assert state["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
            assert all("dummy-" not in value for value in state["Config"]["Env"])
            assert not next(m for m in state["Mounts"] if m["Destination"] == "/run/nmp")["RW"]
            verify = "from naver_mail_mcp.server import _get_credentials; assert _get_credentials() == ('offline@naver.com','dummy-mail-password','')"
            run(compose + ["exec", "-T", "nmp", "python", "-B", "-c", verify])
            health = "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8080/health?details=true',timeout=4)); assert d['components']['control-plane']['status']=='degraded'; assert d['components']['mcp']['details']['child_state']=='running'"
            for _ in range(25):
                result = run(compose + ["exec", "-T", "nmp", "python", "-c", health], check=False)
                if result.returncode == 0:
                    break
                time.sleep(0.5)
            else:
                raise AssertionError(result.stderr)
            time.sleep(10)
            assert inspect()["State"]["Health"]["Status"] == "healthy"
            crash = "import os,signal; from pathlib import Path; pid=int(Path('/proc/1/task/1/children').read_text().split()[0]); assert b'naver_mail_mcp.cli' in Path(f'/proc/{pid}/cmdline').read_bytes(); os.kill(pid,signal.SIGKILL)"
            run(["docker", "exec", container, "python", "-c", crash], check=False)
            for _ in range(25):
                state = inspect()
                if state["RestartCount"] >= 1 and state["State"]["Running"]:
                    break
                time.sleep(0.5)
            else:
                raise AssertionError("Container did not restart after process failure")
            run(compose + ["exec", "-T", "nmp", "python", "-B", "-c", verify])
            print("PASS: encrypted runtime, non-root/read-only, no ports/secrets in Docker config, offline diagnostics and crash restart")
        finally:
            run(compose + ["down", "--timeout", "10"], check=False)
            run(["docker", "volume", "rm", volume])


if __name__ == "__main__":
    main()