import json
from pathlib import Path
from collections import defaultdict
from utils.config import PROJECT_PATH
from utils.project_manager import ProjectManager

def build_project_structure(dependency_analysis_folder: Path, output_file: Path):
    # Data structures to hold the graph and module details
    modules_info = {}
    adjacency_list = defaultdict(list)  # for file-level dependencies

    # Step 1: Gather all JSON files
    json_files = list(dependency_analysis_folder.rglob("*.json"))

    # Step 2: Parse each JSON file and store information
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)

        file_path = data.get("path")  # e.g., "./main.py"
        if not file_path:
            continue

        # Extract details
        classes = data.get("classes", {})
        functions = data.get("functions", {})
        ext_deps = data.get("external_dependencies", [])
        inner_deps = data.get("inner_project_dependencies", {})

        # Flatten inner_deps to get direct module-level paths
        internal_dep_paths = extract_internal_module_paths(inner_deps)

        modules_info[file_path] = {
            "path": file_path,
            "classes": list(classes.keys()),
            "functions": list(functions.keys()),
            "external_dependencies": ext_deps,
            "internal_dependencies": internal_dep_paths
        }

        # Build adjacency list for dependency graph
        for dep_path in internal_dep_paths:
            adjacency_list[file_path].append(dep_path)

    # Step 3: Construct a final project structure
    # For example, a graph-like structure
    project_structure = {
        "modules": modules_info,
        "dependencies_graph": {
            "nodes": list(modules_info.keys()),
            "edges": [{
                "from": src,
                "to": dst
            } for src, targets in adjacency_list.items() for dst in targets]
        }
    }

    # Step 4: Write out the consolidated structure
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(project_structure, f, indent=2)
    print(f"Project structure written to {output_file}")


def extract_internal_module_paths(inner_deps):
    # This function flattens the nested inner_project_dependencies structure
    # to return a list of module file paths (e.g., "./snake.py")
    result = []
    if isinstance(inner_deps, dict):
        # If 'modules' key is present and is a list
        if "modules" in inner_deps and isinstance(inner_deps["modules"], list):
            for mod in inner_deps["modules"]:
                mp = mod.get("path")
                if mp:
                    result.append(mp)
        # Recursively handle sub-dictionaries
        for k, v in inner_deps.items():
            if isinstance(v, dict) or isinstance(v, list):
                result.extend(extract_internal_module_paths(v))
    elif isinstance(inner_deps, list):
        # If it's a list, it may contain modules dicts
        for item in inner_deps:
            if isinstance(item, dict):
                mp = item.get("path")
                if mp:
                    result.append(mp)
                # Also recurse deeper if nested
                result.extend(extract_internal_module_paths(item))
    return list(set(result))  # remove duplicates if any


if __name__ == "__main__":
    project_manager = ProjectManager(
        project_path=PROJECT_PATH
    )
    dependency_analysis_folder = project_manager.get_analysis_folder() / "dependency_analysis"

    output_file = project_manager.get_analysis_folder() /"project_structure.json"
    build_project_structure(dependency_analysis_folder, output_file)
