import asyncio
import json
from pathlib import Path
from utils.project_manager import ProjectManager
from utils.dependency_analyzer import DependencyAnalyzer
from utils.config import PROJECT_PATH

async def main():
    # The entry file: main.py
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

    print(f"[DEBUG] Project path: {PROJECT_PATH.resolve()}")

    analyzer = DependencyAnalyzer(project_manager=project_manager, entry_file=entry_file)
    analyzer.analyze_from_entry()

if __name__ == "__main__":
    asyncio.run(main())
