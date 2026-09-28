"""
Scan a Maven pom.xml and generate structured project metadata.

This component is scan-only.

It extracts:
- Project coordinates
- Parent coordinates
- Java version
- Spring Boot version
- Declared dependencies
- Maven plugins
- Dependency-management entries

It does not:
- modify pom.xml
- update dependencies
- create Git branches
- invoke Groq
- access the internet
"""

import argparse
import json
import re
import xml.etree.ElementTree as element_tree
from pathlib import Path


MAVEN_NAMESPACE = {
    "m": "http://maven.apache.org/POM/4.0.0"
}


def clean_text(value):
    """Return stripped text or None."""

    if value is None:
        return None

    cleaned_value = value.strip()

    if not cleaned_value:
        return None

    return cleaned_value


def child_text(parent, child_name):
    """Read text from a Maven XML child element."""

    if parent is None:
        return None

    child = parent.find(
        "m:{}".format(child_name),
        MAVEN_NAMESPACE,
    )

    if child is None:
        return None

    return clean_text(child.text)


def read_properties(root):
    """Extract all Maven properties."""

    properties = {}

    properties_element = root.find(
        "m:properties",
        MAVEN_NAMESPACE,
    )

    if properties_element is None:
        return properties

    for property_element in list(properties_element):
        property_name = property_element.tag.split("}")[-1]
        property_value = clean_text(property_element.text)

        if property_value is not None:
            properties[property_name] = property_value

    return properties


def resolve_property_value(value, properties, maximum_depth=10):
    """
    Resolve Maven property references.

    Examples:
        ${java.version}
        ${springfox.version}

    Unresolved properties are preserved rather than guessed.
    """

    if value is None:
        return None

    resolved_value = value

    for _ in range(maximum_depth):
        matches = re.findall(
            r"\$\{([^}]+)\}",
            resolved_value,
        )

        if not matches:
            break

        changed = False

        for property_name in matches:
            property_value = properties.get(property_name)

            if property_value is None:
                continue

            placeholder = "${" + property_name + "}"

            resolved_value = resolved_value.replace(
                placeholder,
                property_value,
            )

            changed = True

        if not changed:
            break

    return resolved_value


def parse_coordinates(element, properties):
    """Extract Maven coordinates from an XML element."""

    if element is None:
        return None

    group_id = resolve_property_value(
        child_text(element, "groupId"),
        properties,
    )

    artifact_id = resolve_property_value(
        child_text(element, "artifactId"),
        properties,
    )

    version = resolve_property_value(
        child_text(element, "version"),
        properties,
    )

    return {
        "groupId": group_id,
        "artifactId": artifact_id,
        "version": version,
    }


def parse_dependencies(container, properties):
    """Extract dependencies from a Maven dependency container."""

    dependencies = []

    if container is None:
        return dependencies

    dependency_elements = container.findall(
        "m:dependency",
        MAVEN_NAMESPACE,
    )

    for dependency_element in dependency_elements:
        dependency = {
            "groupId": resolve_property_value(
                child_text(dependency_element, "groupId"),
                properties,
            ),
            "artifactId": resolve_property_value(
                child_text(dependency_element, "artifactId"),
                properties,
            ),
            "version": resolve_property_value(
                child_text(dependency_element, "version"),
                properties,
            ),
            "scope": resolve_property_value(
                child_text(dependency_element, "scope"),
                properties,
            ),
            "type": resolve_property_value(
                child_text(dependency_element, "type"),
                properties,
            ),
            "classifier": resolve_property_value(
                child_text(dependency_element, "classifier"),
                properties,
            ),
            "optional": resolve_property_value(
                child_text(dependency_element, "optional"),
                properties,
            ),
        }

        dependencies.append(dependency)

    return dependencies


def parse_plugins(root, properties):
    """Extract Maven build plugins."""

    plugins = []

    build_element = root.find(
        "m:build",
        MAVEN_NAMESPACE,
    )

    if build_element is None:
        return plugins

    plugins_element = build_element.find(
        "m:plugins",
        MAVEN_NAMESPACE,
    )

    if plugins_element is None:
        return plugins

    plugin_elements = plugins_element.findall(
        "m:plugin",
        MAVEN_NAMESPACE,
    )

    for plugin_element in plugin_elements:
        plugin = {
            "groupId": resolve_property_value(
                child_text(plugin_element, "groupId"),
                properties,
            ),
            "artifactId": resolve_property_value(
                child_text(plugin_element, "artifactId"),
                properties,
            ),
            "version": resolve_property_value(
                child_text(plugin_element, "version"),
                properties,
            ),
        }

        if plugin["groupId"] is None:
            plugin["groupId"] = "org.apache.maven.plugins"

        plugins.append(plugin)

    return plugins


def find_java_version(properties):
    """Find the configured Java source version."""

    candidate_names = [
        "java.version",
        "maven.compiler.release",
        "maven.compiler.source",
        "source.version",
    ]

    for property_name in candidate_names:
        property_value = properties.get(property_name)

        if property_value:
            return {
                "value": property_value,
                "sourceProperty": property_name,
            }

    return {
        "value": None,
        "sourceProperty": None,
    }


def find_spring_boot_version(parent, dependencies, properties):
    """Discover the Spring Boot version."""

    if parent:
        parent_group = parent.get("groupId")
        parent_artifact = parent.get("artifactId")

        if (
            parent_group == "org.springframework.boot"
            and parent_artifact == "spring-boot-starter-parent"
        ):
            return {
                "version": parent.get("version"),
                "source": "parent",
            }

    spring_boot_property = properties.get(
        "spring-boot.version"
    )

    if spring_boot_property:
        return {
            "version": spring_boot_property,
            "source": "property",
        }

    for dependency in dependencies:
        if dependency.get("groupId") == "org.springframework.boot":
            dependency_version = dependency.get("version")

            if dependency_version:
                return {
                    "version": dependency_version,
                    "source": "dependency",
                }

    return {
        "version": None,
        "source": None,
    }


def create_dependency_identifier(dependency):
    """Create a groupId:artifactId identifier."""

    group_id = dependency.get("groupId")
    artifact_id = dependency.get("artifactId")

    if not group_id or not artifact_id:
        return None

    return "{}:{}".format(
        group_id,
        artifact_id,
    )


def scan_pom(pom_file):
    """Scan pom.xml and return structured metadata."""

    pom_path = Path(pom_file).resolve()

    if not pom_path.exists():
        raise FileNotFoundError(
            "pom.xml does not exist: {}".format(pom_path)
        )

    if not pom_path.is_file():
        raise ValueError(
            "POM path is not a file: {}".format(pom_path)
        )

    try:
        xml_tree = element_tree.parse(str(pom_path))
    except element_tree.ParseError as error:
        raise ValueError(
            "Unable to parse pom.xml: {}".format(error)
        )

    root = xml_tree.getroot()
    properties = read_properties(root)

    parent_element = root.find(
        "m:parent",
        MAVEN_NAMESPACE,
    )

    parent = parse_coordinates(
        parent_element,
        properties,
    )

    project_group_id = resolve_property_value(
        child_text(root, "groupId"),
        properties,
    )

    if project_group_id is None and parent:
        project_group_id = parent.get("groupId")

    project_artifact_id = resolve_property_value(
        child_text(root, "artifactId"),
        properties,
    )

    project_version = resolve_property_value(
        child_text(root, "version"),
        properties,
    )

    if project_version is None and parent:
        project_version = parent.get("version")

    packaging = resolve_property_value(
        child_text(root, "packaging"),
        properties,
    )

    if packaging is None:
        packaging = "jar"

    dependencies_element = root.find(
        "m:dependencies",
        MAVEN_NAMESPACE,
    )

    dependencies = parse_dependencies(
        dependencies_element,
        properties,
    )

    dependency_management_element = root.find(
        "m:dependencyManagement/m:dependencies",
        MAVEN_NAMESPACE,
    )

    managed_dependencies = parse_dependencies(
        dependency_management_element,
        properties,
    )

    plugins = parse_plugins(
        root,
        properties,
    )

    java_version = find_java_version(properties)

    spring_boot = find_spring_boot_version(
        parent,
        dependencies,
        properties,
    )

    for dependency in dependencies:
        dependency["identifier"] = create_dependency_identifier(
            dependency
        )

    for dependency in managed_dependencies:
        dependency["identifier"] = create_dependency_identifier(
            dependency
        )

    return {
        "pomFile": str(pom_path),
        "project": {
            "groupId": project_group_id,
            "artifactId": project_artifact_id,
            "version": project_version,
            "packaging": packaging,
        },
        "parent": parent,
        "platform": {
            "javaVersion": java_version,
            "springBoot": spring_boot,
        },
        "properties": properties,
        "dependencies": dependencies,
        "dependencyManagement": managed_dependencies,
        "plugins": plugins,
        "summary": {
            "dependencyCount": len(dependencies),
            "managedDependencyCount": len(
                managed_dependencies
            ),
            "pluginCount": len(plugins),
        },
    }


def write_report(scan_result, output_file):
    """Write the POM scan result as formatted JSON."""

    output_path = Path(output_file).resolve()

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(scan_result, indent=2),
        encoding="utf-8",
    )

    return output_path


def print_summary(scan_result, report_path):
    """Print a concise POM scan summary."""

    project = scan_result.get("project", {})
    platform = scan_result.get("platform", {})
    summary = scan_result.get("summary", {})

    java_information = platform.get(
        "javaVersion",
        {},
    )

    spring_boot_information = platform.get(
        "springBoot",
        {},
    )

    java_version = java_information.get("value")
    spring_boot_version = spring_boot_information.get(
        "version"
    )

    print("=" * 60)
    print("MAVEN POM SCAN")
    print("=" * 60)

    print(
        "Project             : {}:{}".format(
            project.get("groupId"),
            project.get("artifactId"),
        )
    )

    print(
        "Project version     : {}".format(
            project.get("version")
        )
    )

    print(
        "Packaging           : {}".format(
            project.get("packaging")
        )
    )

    print(
        "Java version        : {}".format(
            java_version
        )
    )

    print(
        "Spring Boot version : {}".format(
            spring_boot_version
        )
    )

    print(
        "Dependencies        : {}".format(
            summary.get("dependencyCount", 0)
        )
    )

    print(
        "Managed dependencies: {}".format(
            summary.get("managedDependencyCount", 0)
        )
    )

    print(
        "Plugins             : {}".format(
            summary.get("pluginCount", 0)
        )
    )

    print("Declared dependencies:")

    dependencies = scan_result.get(
        "dependencies",
        [],
    )

    for dependency in dependencies:
        version = dependency.get("version")

        if version is None:
            version = "managed-or-inherited"

        print(
            "  - {}:{}:{}".format(
                dependency.get("groupId"),
                dependency.get("artifactId"),
                version,
            )
        )

    print(
        "Report              : {}".format(
            report_path
        )
    )


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Scan a Maven pom.xml file."
    )

    parser.add_argument(
        "--pom",
        default="pom.xml",
        help="Path to pom.xml.",
    )

    parser.add_argument(
        "--output",
        default="migration-agent/reports/pom-scan.json",
        help="Path for the generated JSON report.",
    )

    args = parser.parse_args()

    try:
        scan_result = scan_pom(args.pom)

        report_path = write_report(
            scan_result,
            args.output,
        )

        print_summary(
            scan_result,
            report_path,
        )

        return 0

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print(
            "Unexpected POM scanner error: {}".format(
                error
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())