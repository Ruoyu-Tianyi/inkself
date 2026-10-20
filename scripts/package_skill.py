"""Package only the reusable skill; never include profiles or samples."""
import argparse
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('dist/personal-handwriting.zip'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'skills' / 'personal-handwriting'
    target = args.output.resolve()
    if target.exists():
        parser.error('Output exists; choose a new output path.')
    target.parent.mkdir(parents=True, exist_ok=True)
    allowed = [root/'SKILL.md', root/'requirements.txt', *sorted((root/'references').glob('*.md')),
               *sorted((root/'scripts').glob('*.py'))]
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in allowed:
            archive.write(path, Path(root.name) / path.relative_to(root))
    print(target)


if __name__ == '__main__':
    main()
