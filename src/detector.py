import sys
import yaml
import requests
from rich.console import Console
from rich.table import Table
from datetime import datetime

console = Console()

def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

def github_get(url: str, token: str) -> dict | list | None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def check_secrets(repo: str, expected: list, token: str) -> list:
    data = github_get(f"https://api.github.com/repos/{repo}/actions/secrets", token)
    real_secrets = [s["name"] for s in data.get("secrets", [])] if data else []
    results = []
    for secret in expected:
        name = secret["name"]
        status = "✅ ok" if name in real_secrets else "❌ missing"
        results.append(("Secret", name, "-", status))
    return results

def check_variables(repo: str, expected: list, token: str) -> list:
    data = github_get(f"https://api.github.com/repos/{repo}/actions/variables", token)
    real_vars = {v["name"]: v["value"] for v in data.get("variables", [])} if data else {}
    results = []
    for var in expected:
        name = var["name"]
        expected_value = var.get("value")
        if name not in real_vars:
            results.append(("Variable", name, expected_value or "-", "❌ missing"))
        elif expected_value and real_vars[name] != expected_value:
            results.append(("Variable", name, f"expected={expected_value} got={real_vars[name]}", "⚠️  drift"))
        else:
            results.append(("Variable", name, expected_value or "-", "✅ ok"))
    return results

def check_branch_protection(repo: str, expected: list, token: str) -> list:
    results = []
    for rule in expected:
        branch = rule["branch"]
        data = github_get(f"https://api.github.com/repos/{repo}/branches/{branch}/protection", token)
        if data is None:
            results.append(("Branch Protection", branch, "require_pr=true", "❌ missing"))
            continue
        has_pr = data.get("required_pull_request_reviews") is not None
        status = "✅ ok" if has_pr == rule.get("require_pr", False) else "⚠️  drift"
        results.append(("Branch Protection", branch, f"require_pr={rule.get('require_pr')}", status))
    return results

def print_table(results: list):
    table = Table(title="Infra Drift Report", show_lines=True)
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Expected", style="yellow")
    table.add_column("Status", style="bold")
    for row in results:
        table.add_row(*row)
    console.print(table)

def save_report(results: list, repo: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"reports/drift-report-{timestamp}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Infra Drift Report\n")
        f.write(f"**Repo:** {repo}  \n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("| Type | Name | Expected | Status |\n")
        f.write("|------|------|----------|--------|\n")
        for row in results:
            f.write(f"| {' | '.join(row)} |\n")
    console.print(f"\n[dim]Report saved to {path}[/dim]")

def main():
    config = load_config("config/expected.yml")
    repo = config["repository"]
    token = sys.argv[1] if len(sys.argv) > 1 else ""

    if not token:
        console.print("[red]Error: GitHub token required as argument[/red]")
        console.print("Usage: python src/detector.py <github_token>")
        sys.exit(1)

    console.print(f"\n[bold cyan]Checking repo:[/bold cyan] {repo}\n")

    results = []
    results += check_secrets(repo, config["expected"].get("secrets", []), token)
    results += check_variables(repo, config["expected"].get("variables", []), token)
    results += check_branch_protection(repo, config["expected"].get("branch_protection", []), token)

    print_table(results)
    save_report(results, repo)

if __name__ == "__main__":
    main()