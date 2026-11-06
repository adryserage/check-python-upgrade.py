#!/usr/bin/env python3
"""
Enhanced Python Package Dependency Resolver
Analyzes requirements.txt and automatically fixes dependency conflicts.
"""

import argparse
import subprocess
import sys
import shutil
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class DependencyResolver:
    def __init__(self, requirements_file: str):
        self.requirements_file = Path(requirements_file)
        self.backup_file = None
        self.conflicts_found = []
        self.fixes_applied = []

        # Known working version combinations
        self.known_combinations = {
            # LangChain ecosystem - compatible versions
            "langchain_ecosystem": {
                "google-generativeai": "0.7.2",
                "langchain": "0.2.16",
                "langchain-community": "0.2.16",
                "langchain-google-genai": "1.0.10",
                # Don't pin langchain-core, let it resolve automatically
            },
            # Django ecosystem
            "django_ecosystem": {
                "django": "5.1.4",  # Stable version
                "djangorestframework": "3.15.2",
                "django-cors-headers": "4.4.0",
                "django-redis": "5.4.0",
            },
            # FastAPI ecosystem
            "fastapi_ecosystem": {
                "fastapi": "0.115.4",
                "uvicorn[standard]": "0.32.0",
                "pydantic": "2.10.3",  # Stable version, not alpha
            },
        }

    def create_backup(self):
        """Create a backup of the original requirements file"""
        self.backup_file = f"{self.requirements_file}.backup"
        shutil.copy2(self.requirements_file, self.backup_file)
        print(f"📁 Created backup: {self.backup_file}")

    def parse_requirements(self) -> List[Tuple[str, str, str]]:
        """Parse requirements.txt and return list of (package, version, original_line)"""
        packages = []

        with open(self.requirements_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line_num, line in enumerate(lines, 1):
            original_line = line.strip()

            # Skip comments and empty lines
            if not line.strip() or line.strip().startswith("#"):
                packages.append((None, None, original_line))
                continue

            # Parse package==version format
            if "==" in line:
                try:
                    package_part, version = line.strip().split("==", 1)
                    # Handle extras like package[extra]==version
                    package_name = package_part.split("[")[0].strip()
                    packages.append((package_name, version.strip(), original_line))
                except ValueError:
                    packages.append((None, None, original_line))
            else:
                packages.append((None, None, original_line))

        return packages

    def check_for_conflicts(self) -> bool:
        """Check if current requirements have conflicts"""
        print("🔍 Checking for dependency conflicts...")

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--dry-run",
                    "-r",
                    str(self.requirements_file),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                print("✅ No conflicts detected!")
                return False
            else:
                print("❌ Conflicts detected!")
                self.parse_conflict_output(result.stderr)
                return True

        except subprocess.TimeoutExpired:
            print("⏰ Timeout checking dependencies")
            return True
        except Exception as e:
            print(f"❌ Error checking dependencies: {e}")
            return True

    def parse_conflict_output(self, error_output: str):
        """Parse pip error output to identify specific conflicts"""
        lines = error_output.split("\n")
        current_conflict = {}

        for line in lines:
            if "conflict" in line.lower() or "cannot install" in line.lower():
                # Extract package names from conflict messages
                packages = re.findall(r"([a-zA-Z0-9_-]+)==?([0-9.a-zA-Z]+)", line)
                if packages:
                    self.conflicts_found.extend(packages)

        print(
            f"🔍 Found conflicts involving: {', '.join(set(p[0] for p in self.conflicts_found))}"
        )

    def apply_smart_fixes(self) -> bool:
        """Apply intelligent fixes based on known working combinations"""
        packages = self.parse_requirements()
        package_dict = {pkg: (ver, line) for pkg, ver, line in packages if pkg}

        fixes_needed = False
        updated_lines = []

        # Check each ecosystem for conflicts and apply fixes
        for ecosystem_name, versions in self.known_combinations.items():
            ecosystem_packages = set(versions.keys()) & set(package_dict.keys())

            if len(ecosystem_packages) > 1:  # Multiple packages from same ecosystem
                print(f"\n🔧 Applying {ecosystem_name} fixes...")

                for pkg_name, target_version in versions.items():
                    if pkg_name in package_dict:
                        current_version = package_dict[pkg_name][0]
                        if current_version != target_version:
                            self.fixes_applied.append(
                                f"{pkg_name}: {current_version} → {target_version}"
                            )
                            fixes_needed = True

        # Rebuild requirements with fixes
        for pkg, ver, original_line in packages:
            if pkg is None:  # Comment or empty line
                updated_lines.append(original_line)
            else:
                # Check if this package needs fixing
                fixed_version = None
                for ecosystem_versions in self.known_combinations.values():
                    if pkg in ecosystem_versions:
                        fixed_version = ecosystem_versions[pkg]
                        break

                if fixed_version and fixed_version != ver:
                    # Apply fix
                    if "[" in original_line:
                        # Handle extras like uvicorn[standard]==version
                        base_pkg, rest = original_line.split("==", 1)
                        updated_lines.append(f"{base_pkg}=={fixed_version}")
                    else:
                        updated_lines.append(f"{pkg}=={fixed_version}")
                else:
                    updated_lines.append(original_line)

        if fixes_needed:
            # Write updated requirements
            with open(self.requirements_file, "w", encoding="utf-8") as f:
                for line in updated_lines:
                    f.write(line + "\n" if not line.endswith("\n") else line)

            print(f"\n✅ Applied {len(self.fixes_applied)} fixes:")
            for fix in self.fixes_applied:
                print(f"  - {fix}")

        return fixes_needed

    def remove_problematic_packages(self) -> bool:
        """Remove packages that are causing unresolvable conflicts"""
        packages = self.parse_requirements()

        # Packages to potentially remove (usually auto-installed as dependencies)
        removable_packages = {}

        updated_lines = []
        removed_packages = []

        for pkg, ver, original_line in packages:
            if pkg in removable_packages:
                removed_packages.append(pkg)
                print(f"🗑️  Removing {pkg} (will be installed as dependency)")
                continue
            else:
                updated_lines.append(original_line)

        if removed_packages:
            with open(self.requirements_file, "w", encoding="utf-8") as f:
                for line in updated_lines:
                    f.write(line + "\n" if not line.endswith("\n") else line)
            return True

        return False

    def test_final_result(self) -> bool:
        """Test if the final requirements can be installed"""
        print("\n🧪 Testing final configuration...")

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--dry-run",
                    "-r",
                    str(self.requirements_file),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                print(
                    "✅ Success! Requirements can now be installed without conflicts."
                )
                return True
            else:
                print("❌ Still has some conflicts:")
                # Show only critical errors
                for line in result.stderr.split("\n"):
                    if "ERROR:" in line or "conflict" in line.lower():
                        print(f"  {line}")
                return False

        except Exception as e:
            print(f"❌ Error testing final result: {e}")
            return False

    def resolve(self) -> bool:
        """Main resolution process"""
        print(f"🔧 Dependency Resolver for {self.requirements_file.name}")
        print("=" * 60)

        # Step 1: Check for conflicts
        if not self.check_for_conflicts():
            print("🎉 No conflicts found! Your requirements are already compatible.")
            return True

        # Step 2: Create backup
        self.create_backup()

        # Step 3: Remove problematic packages first
        print("\n🗑️  Removing auto-managed packages...")
        self.remove_problematic_packages()

        # Step 4: Apply smart fixes
        print("\n🔧 Applying compatibility fixes...")
        self.apply_smart_fixes()

        # Step 5: Test result
        success = self.test_final_result()

        if success:
            print(f"\n🎉 Resolution complete! Backup saved as: {self.backup_file}")
        else:
            print(f"\n⚠️  Partial success. Some manual intervention may be needed.")
            print(f"💾 Backup available at: {self.backup_file}")

        return success


def main():
    parser = argparse.ArgumentParser(
        description="Resolve Python package dependency conflicts"
    )
    parser.add_argument("requirements_file", help="Path to requirements.txt file")
    parser.add_argument(
        "--test-only", action="store_true", help="Only test for conflicts"
    )

    args = parser.parse_args()

    if not Path(args.requirements_file).exists():
        print(f"❌ File not found: {args.requirements_file}")
        sys.exit(1)

    resolver = DependencyResolver(args.requirements_file)

    if args.test_only:
        has_conflicts = resolver.check_for_conflicts()
        sys.exit(1 if has_conflicts else 0)
    else:
        success = resolver.resolve()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
