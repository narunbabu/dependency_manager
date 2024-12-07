import ast
import sys
import json
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from utils.project_manager import ProjectManager

class DependencyAnalyzer:
    def __init__(self, project_manager: ProjectManager, entry_file: Path, max_depth: Optional[int] = None):
        self.project_manager = project_manager
        self.project_path = self.project_manager.get_project_folder()
        self.entry_file = entry_file.resolve()
        self.max_depth = max_depth
        self.standard_modules = self.get_standard_modules()
        self.visited: Set[Path] = set()  # Prevent infinite loops
        self.logger = self.project_manager.logger
        self.dependency_analysis_folder = self.project_manager.get_analysis_folder() / "dependency_analysis"

    def get_standard_modules(self) -> set:
        """
        Get a set of built-in module names for exclusion.
        """
        std_modules = set(sys.builtin_module_names)
        # Optionally, add more standard library modules if needed
        return std_modules

    def analyze_from_entry(self):
        """
        Start analyzing dependencies from the specified entry file (e.g., main.py).
        """
        if not self.entry_file.exists():
            self.logger.error(f"Entry file {self.entry_file} does not exist.")
            return
        self._recursive_analyze_file(self.entry_file)

    def _recursive_analyze_file(self, file_path: Path, depth: int = 0):
        if self.max_depth is not None and depth > self.max_depth:
            self.logger.debug(f"Max depth {self.max_depth} reached at {file_path}")
            return
        if file_path in self.visited:
            self.logger.debug(f"Already visited {file_path}")
            return
        self.visited.add(file_path)

        file_info = self._analyze_single_file(file_path)
        self._write_file_info_to_json(file_path, file_info)

        inner_deps = file_info.get("inner_project_dependencies", {})
        self._recurse_inner_dependencies(inner_deps, depth)

    def _recurse_inner_dependencies(self, deps, depth):
        """
        Recurse through the 'inner_project_dependencies' structure
        and analyze each discovered file.
        Handles both nested modules within subdirectories and modules in the main directory.
        """
        for key, val in deps.items():
            self.logger.debug(f"Processing key: {key}, val: {val}")
            if key == 'modules' and isinstance(val, list):
                # Handle list of modules directly under 'modules' key
                for mod in val:
                    mod_path = mod.get("path")
                    if mod_path:
                        mod_real_path = (self.project_path / mod_path.strip('./')).resolve()
                        self.logger.debug(f"Resolved module path: {mod_real_path}")
                        if mod_real_path.exists():
                            self._recursive_analyze_file(mod_real_path, depth + 1)
                        else:
                            self.logger.warning(f"Module path does not exist: {mod_real_path}")
            elif isinstance(val, dict):
                # Handle nested directories/modules
                if "modules" in val and isinstance(val["modules"], list):
                    for mod in val["modules"]:
                        mod_path = mod.get("path")
                        if mod_path:
                            mod_real_path = (self.project_path / mod_path.strip('./')).resolve()
                            self.logger.debug(f"Resolved nested module path: {mod_real_path}")
                            if mod_real_path.exists():
                                self._recursive_analyze_file(mod_real_path, depth + 1)
                            else:
                                self.logger.warning(f"Nested module path does not exist: {mod_real_path}")
                else:
                    # If there are other nested dictionaries, recurse further
                    self._recurse_inner_dependencies(val, depth)
            elif isinstance(val, list):
                # Handle lists not under 'modules' key (if any)
                for mod in val:
                    if isinstance(mod, dict):
                        mod_path = mod.get("path")
                        if mod_path:
                            mod_real_path = (self.project_path / mod_path.strip('./')).resolve()
                            self.logger.debug(f"Resolved module path from list: {mod_real_path}")
                            if mod_real_path.exists():
                                self._recursive_analyze_file(mod_real_path, depth + 1)
                            else:
                                self.logger.warning(f"Module path from list does not exist: {mod_real_path}")
            else:
                # Handle other possible structures if necessary
                self.logger.debug(f"Unhandled dependency structure for key: {key}, val: {val}")

    def _analyze_single_file(self, file_path: Path) -> Dict:
        """
        Parse a single file, find its imports and classify them as internal or external.
        Also extract classes, functions, etc.
        """
        self.logger.info(f"Analyzing {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError) as e:
            self.logger.error(f"Failed to parse {file_path}: {e}")
            return {"path": str(file_path), "error": str(e)}

        visitor = DependencyVisitor(file_path, self.standard_modules, self.project_path)
        visitor.analyze_source_code(source)

        # Resolve imports into internal/external
        internal_deps, external_deps = self._classify_imports(visitor.file_info["imports"])

        # Construct the JSON structure
        inner_deps_structure = self._build_inner_deps_structure(internal_deps)

        file_info = {
            "path": "./" + str(file_path.relative_to(self.project_path)),
            "inner_project_dependencies": inner_deps_structure,
            "external_dependencies": external_deps,
            "classes": visitor.file_info.get("classes", {}),
            "functions": visitor.file_info.get("functions", {})
        }

        return file_info

    def _classify_imports(self, imports: List[str]) -> Tuple[List[Tuple[str, Path, List[str]]], List[str]]:
        """
        Classify imports into:
        - Internal: (import_name, resolved_file_path, [sub_modules]) 
        - External: just a list of import names

        We try to resolve each import to a file in the project.
        If found, it's internal. Otherwise external.
        """
        internal = []
        external = []
        for imp in imports:
            result = self._resolve_import(imp)
            if result is not None:
                internal.append(result)
            else:
                external.append(imp)
        return internal, external

    def _resolve_import(self, import_name: str) -> Optional[Tuple[str, Path, List[str]]]:
        """
        Try to resolve an import (like 'snake' or 'widgets.MapPlot') to a file inside the project.
        If found, return a tuple of (module_name, file_path, [sub_modules]).
        Otherwise, return None.
        """
        parts = import_name.split('.')
        for i in range(len(parts), 0, -1):
            prefix = parts[:i]
            candidate_file = self._find_module_file(prefix)
            if candidate_file is not None:
                sub_modules = parts[i:] if i < len(parts) else []
                return (prefix[-1], candidate_file, sub_modules)
        return None

    def _find_module_file(self, parts: List[str]) -> Optional[Path]:
        """
        Given a list of parts from an import, try to find a corresponding .py file or package.
        """
        base = self.project_path

        if len(parts) == 1:
            # Single module, could be a .py file or a package directory
            single_name = parts[0]
            file_candidate = base / (single_name + ".py")
            if file_candidate.exists():
                return file_candidate.resolve()

            # Check for package directory
            dir_candidate = base / single_name
            init_candidate = dir_candidate / "__init__.py"
            if dir_candidate.exists() and init_candidate.exists():
                return init_candidate.resolve()
            return None

        # Multiple parts, traverse directories
        for p in parts[:-1]:
            base = base / p
            if not base.exists() or not base.is_dir():
                return None

        last_part = parts[-1]
        file_candidate = base / (last_part + ".py")
        if file_candidate.exists():
            return file_candidate.resolve()

        # Check for package directory
        dir_candidate = base / last_part
        init_candidate = dir_candidate / "__init__.py"
        if dir_candidate.exists() and init_candidate.exists():
            return init_candidate.resolve()

        return None

    def _build_inner_deps_structure(self, internal_deps: List[Tuple[str, Path, List[str]]]) -> Dict:
        """
        Build a nested dictionary structure for internal dependencies:
        {
          "modules": [
              {"name": "snake", "path": "./snake.py", "sub_modules": ["Snake"]},
              {"name": "food", "path": "./food.py", "sub_modules": ["Food"]},
              ...
          ],
          "widgets": {
              "path": "./widgets",
              "modules": [
                  {"name": "MapPlot", "path": "./widgets/MapPlot.py", "sub_modules": ["MapWidget"]},
                  ...
              ]
          }
        }
        """
        structure = {}
        for (name, path, sub_modules) in internal_deps:
            rel_path = path.relative_to(self.project_path)
            parts = rel_path.parts[:-1]  # Directories leading up to the file
            file_name = rel_path.stem
            current = structure

            # Navigate through nested directories
            for p in parts:
                if p not in current:
                    current[p] = {
                        'path': './' + str(Path(*rel_path.parts[:rel_path.parts.index(p)+1]))
                    }
                current = current[p]

            # Add module information under 'modules' key
            if 'modules' not in current:
                current['modules'] = []
            current['modules'].append({
                'name': file_name,
                'path': './' + str(rel_path),
                'sub_modules': sub_modules
            })
        return structure

    def _write_file_info_to_json(self, file_path: Path, file_info: Dict):
        """
        Write the file_info dict to a JSON file in the dependency_analysis_folder,
        maintaining the project structure in the output folder.
        """
        rel_path = file_path.relative_to(self.project_path)
        target_dir = self.dependency_analysis_folder / rel_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / (rel_path.stem + ".json")

        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(file_info, f, indent=2)
        self.logger.info(f"Wrote analysis to {target_file}")

class DependencyVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, standard_modules: set, project_path: Path):
        self.file_path = str(file_path)
        self.standard_modules = standard_modules
        self.project_path = project_path
        self.file_info = {
            "classes": {},
            "functions": {},
            "imports": [],
        }
        self.current_class = None
        self.current_function = None
        self.source_code = ""

    def analyze_source_code(self, source_code: str):
        self.source_code = source_code
        tree = ast.parse(source_code)
        self.visit(tree)

    def visit_Import(self, node):
        for alias in node.names:
            self.file_info["imports"].append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module if node.module else ""
        imported_names = [alias.name for alias in node.names]
        if module:
            for name in imported_names:
                self.file_info["imports"].append(f"{module}.{name}")
        else:
            for name in imported_names:
                self.file_info["imports"].append(name)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        class_info = {
            "name": node.name,
            "type": "class",
            "start_line": node.lineno,
            "end_line": getattr(node, 'end_lineno', None),
            "docstring": ast.get_docstring(node),
            "methods": {},
            "bases": [self._get_name(base) for base in node.bases],
        }
        self.file_info["classes"][node.name] = class_info
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = None

    def visit_FunctionDef(self, node):
        function_info = {
            "name": node.name,
            "type": "method" if self.current_class else "function",
            "start_line": node.lineno,
            "end_line": getattr(node, 'end_lineno', None),
            "docstring": ast.get_docstring(node),
            "calls": [],
            "variables": {"used": [], "assigned": []},
            "decorators": [self._get_full_name(dec) for dec in node.decorator_list],
            "returns": self._get_annotation(node.returns),
            "parameters": self._get_parameters(node.args),
        }
        if self.current_class:
            self.file_info["classes"][self.current_class]["methods"][node.name] = function_info
        else:
            self.file_info["functions"][node.name] = function_info

        self.current_function = function_info
        self.generic_visit(node)
        self.current_function = None

    def visit_Call(self, node):
        func_name = self._get_full_name(node.func)
        if self.current_function:
            self.current_function["calls"].append(func_name)
        self.generic_visit(node)

    def visit_Name(self, node):
        if self.current_function:
            if isinstance(node.ctx, ast.Load):
                if node.id not in self.current_function["variables"]["used"]:
                    self.current_function["variables"]["used"].append(node.id)
            elif isinstance(node.ctx, ast.Store):
                if node.id not in self.current_function["variables"]["assigned"]:
                    self.current_function["variables"]["assigned"].append(node.id)
        self.generic_visit(node)

    def _get_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_full_name(node)
        return ""

    def _get_full_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value_name = self._get_full_name(node.value)
            return f"{value_name}.{node.attr}" if value_name else node.attr
        elif isinstance(node, ast.Call):
            return self._get_full_name(node.func)
        elif isinstance(node, ast.Subscript):
            return self._get_full_name(node.value)
        return ""

    def _get_annotation(self, node):
        if node is None:
            return None
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Subscript):
            return self._get_full_name(node)
        else:
            return ast.dump(node)

    def _get_parameters(self, args):
        parameters = []
        for arg in args.args:
            param = {
                "name": arg.arg,
                "annotation": self._get_annotation(arg.annotation)
            }
            parameters.append(param)
        return parameters
