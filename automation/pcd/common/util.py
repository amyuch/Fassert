import subprocess
import sys

def run_cmd(cmd, print_stdout=True, print_stderr=True, print_cmd=True) -> subprocess.CompletedProcess:
    if print_cmd:
        print(f"Executing: {cmd}")
    result = subprocess.run(cmd, text=True, shell=True, capture_output=True)
    if print_stdout and result.stdout:
        print(result.stdout)
    if print_stderr and result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        print(f"WARNING: Command returned non-zero exit code {result.returncode}")
    return result

def parse_config(config_file):
    config = {}
    with open(config_file, 'r') as f:
        lines = f.readlines()
        for line in lines:
            if "=" in line:
                key, val = line.strip().split("=", 1)
                config[key] = val
    return config

def write_back_config(config, config_file):
    with open(config_file, "w") as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
