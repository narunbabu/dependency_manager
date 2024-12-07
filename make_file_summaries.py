import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from utils.project_manager import ProjectManager
from utils.dependency_analyzer import DependencyAnalyzer
from utils.config import PROJECT_PATH


async def main():
    # Configuration and initialization
    entry_file = PROJECT_PATH / "main.py"
    if not entry_file.exists():
        print(f"Entry file {entry_file} does not exist.")
        return

    ignored_dirs = ['tests', '__pycache__', 'migrations', 'dist','build','.ipynb_checkpoints','assets','unused' ]
    ignored_files = ['setup.py', 'manage.py']
    ignored_path_substrings = ['legacy', 'third_party','__pycache__']

    project_manager = ProjectManager(
        project_path=PROJECT_PATH,
        ignored_dirs=ignored_dirs,
        ignored_files=ignored_files,
        ignored_path_substrings=ignored_path_substrings
    )

    project_manager.initialize_logger()
    project_manager.setup_workspace(clean_existing=False)
    logger = project_manager.logger

    logger.info(f"[DEBUG] Project path: {PROJECT_PATH.resolve()}")

    # Perform dependency analysis
    analyzer = DependencyAnalyzer(project_manager=project_manager, entry_file=entry_file)
    analyzer.analyze_from_entry()

    # Steps beyond dependency analysis:
    # 1. Copy dependent files into actual_code folder (only those analyzed)
    dependency_analysis_folder = project_manager.get_analysis_folder() / "dependency_analysis"
    actual_code_folder = project_manager.get_analysis_folder() / "actual_code"
    logger.info("Copying dependent files to actual_code folder...")
    copy_dependent_files(dependency_analysis_folder, actual_code_folder, PROJECT_PATH, logger)

    # 2. Run the Python program in terminal from actual_code_folder
    logger.info("Running the python program from actual_code_folder...")
    output, error, returncode = run_program(actual_code_folder, "main.py")

    # 3. Capture terminal logs - we already have output, error as strings
    # 4. Analyze the terminal logs to see if there is an error
    error_lines = []
    if returncode != 0:
        logger.info("Program exited with an error. Analyzing traceback...")
        error_lines = parse_error_output(error + "\n" + output)

        # 5. Extract the affected code and dependency code
        # We'll lookup lines from error messages and cross-reference with JSON files
        code_excerpts = extract_code_excerpts(error_lines, actual_code_folder, dependency_analysis_folder, logger)

        # 6. Writing the text file with the captured error lines from terminal
        write_error_report(project_manager.get_analysis_folder(), error_lines, code_excerpts, logger)
    else:
        logger.info("Program ran successfully without errors.")


def copy_dependent_files(dependency_analysis_folder: Path, actual_code_folder: Path, project_path: Path, logger):
    """
    Copies the dependent source files identified by the JSON files in dependency_analysis_folder
    into the actual_code_folder, preserving directory structure.
    We scan all JSON files for their "path" attribute to find which .py files to copy.
    """
    if actual_code_folder.exists():
        shutil.rmtree(actual_code_folder)
    actual_code_folder.mkdir(parents=True, exist_ok=True)

    # Collect all json files from dependency_analysis_folder
    json_files = list(dependency_analysis_folder.rglob("*.json"))
    copied = set()
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
        py_path = data.get("path")
        if py_path:
            # py_path is like "./widgets/MapPlot.py", resolve relative to project_path
            py_source = (project_path / py_path.strip("./")).resolve()
            if py_source.exists():
                target = actual_code_folder / py_source.relative_to(project_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                if py_source not in copied:
                    shutil.copy2(py_source, target)
                    copied.add(py_source)

    logger.info(f"Copied {len(copied)} dependent files into {actual_code_folder}")


def run_program(working_dir: Path, entry_script: str):
    """
    Run the python program from working_dir and capture its stdout, stderr, and return code.
    """
    cmd = ["python", entry_script]
    process = subprocess.Popen(
        cmd, cwd=working_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    out, err = process.communicate()
    return out, err, process.returncode


def parse_error_output(error_output: str):
    """
    Parse the error output (which includes traceback).
    We'll look for lines like:
    File "C:/path/to/file.py", line X, in <module/function>
    Return a list of tuples: [(file_path, line_number), ...]
    """
    import re
    pattern = r'File "(.+?)", line (\d+),'
    matches = re.findall(pattern, error_output)
    # matches is [(file_path, line_str), ...]
    # We also keep the raw lines of traceback to put in the report
    return [(m[0], int(m[1])) for m in matches]


def extract_code_excerpts(error_lines, actual_code_folder: Path, dependency_analysis_folder: Path, logger):
    """
    Given the list of (file_path, line_number) from the error traceback, extract some context.
    We can extract a few lines around the error line to show context.
    Also we can use the dependency_analysis json to find the classes/functions near that line.
    """
    code_context = {}
    for file_path, line_num in error_lines:
        # file_path might be absolute. We need to see if it is inside actual_code_folder.
        # If not inside actual_code_folder, it's likely an external file (no code excerpt)
        rel_path = None
        try:
            rel_path = Path(file_path).resolve().relative_to(actual_code_folder.resolve())
        except ValueError:
            # Not inside actual_code_folder
            continue

        # Extract code lines around this line from actual_code_folder
        code_excerpt = get_code_excerpt(actual_code_folder / rel_path, line_num)
        # Find JSON analysis if available
        json_info = get_json_info_for_file(dependency_analysis_folder, rel_path, logger)
        nearest_entity = find_nearest_entity(json_info, line_num)

        code_context[str(rel_path)] = {
            "error_line": line_num,
            "code_excerpt": code_excerpt,
            "nearest_entity": nearest_entity
        }

    return code_context


def get_code_excerpt(file_path: Path, line_num: int, context=5):
    lines = file_path.read_text(encoding="utf-8").splitlines()
    start = max(0, line_num - context - 1)
    end = min(len(lines), line_num + context)
    excerpt = []
    for i in range(start, end):
        prefix = ">> " if (i+1) == line_num else "   "
        excerpt.append(f"{prefix}{i+1}: {lines[i]}")
    return excerpt


def get_json_info_for_file(dependency_analysis_folder: Path, rel_path: Path, logger):
    """
    Given a relative path like 'widgets/MapPlot.py', find its json in dependency_analysis_folder
    """
    json_path = dependency_analysis_folder / rel_path.parent / (rel_path.stem + ".json")
    if json_path.exists():
        with json_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    else:
        logger.warning(f"No JSON analysis found for {rel_path}")
        return {}


def find_nearest_entity(json_info: dict, line_num: int):
    """
    Given the JSON info, find the nearest class or function definition around the error line.
    Check classes and their methods, and top-level functions.
    """
    best_match = None
    best_distance = float('inf')

    # Check classes
    classes = json_info.get("classes", {})
    for cls_name, cls_data in classes.items():
        cls_start = cls_data.get("start_line", 0)
        cls_end = cls_data.get("end_line", 0)
        if cls_start <= line_num <= cls_end:
            # Inside this class. Check methods too
            methods = cls_data.get("methods", {})
            for m_name, m_data in methods.items():
                m_start = m_data.get("start_line", 0)
                m_end = m_data.get("end_line", 0)
                if m_start <= line_num <= m_end:
                    # Inside this method
                    dist = 0  # exact match inside method
                    if dist < best_distance:
                        best_distance = dist
                        best_match = f"Method {m_name} of class {cls_name}"
                else:
                    # Not inside any method, but inside class
                    # The class itself is a nearest entity
                    dist = min(abs(line_num - cls_start), abs(line_num - cls_end))
                    if dist < best_distance:
                        best_distance = dist
                        best_match = f"Inside class {cls_name}"
    
    # Check top-level functions if no class matched
    if best_match is None:
        functions = json_info.get("functions", {})
        for f_name, f_data in functions.items():
            f_start = f_data.get("start_line", 0)
            f_end = f_data.get("end_line", 0)
            if f_start <= line_num <= f_end:
                dist = 0
                if dist < best_distance:
                    best_distance = dist
                    best_match = f"Function {f_name}"
            else:
                dist = min(abs(line_num - f_start), abs(line_num - f_end))
                if dist < best_distance:
                    best_distance = dist
                    best_match = f"Near function {f_name}"

    return best_match or "No nearby entity found"


def write_error_report(analysis_folder: Path, error_lines, code_excerpts, logger):
    report_path = analysis_folder / "error_report.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("=== Error Report ===\n\n")
        f.write("Traceback files and lines:\n")
        for file_path, line_num in error_lines:
            f.write(f"File: {file_path}, Line: {line_num}\n")
            rel_key = None
            # Attempt to find if we got an excerpt
            for k in code_excerpts.keys():
                # k is str of rel_path, we must check if file_path ends with k
                if Path(file_path).name == Path(k).name:
                    rel_key = k
                    break
            if rel_key:
                info = code_excerpts[rel_key]
                f.write("\nCode Excerpt around error:\n")
                for l in info["code_excerpt"]:
                    f.write(l + "\n")
                f.write(f"\nNearest Entity: {info['nearest_entity']}\n\n")
        f.write("=== End of Report ===\n")

    logger.info(f"Error report written to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
