"""Run a synthetic-font fixture through the complete pipeline, NOT a personal similarity demo."""
from pathlib import Path
import argparse
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pipeline_fixtures', ROOT/'tests/test_pipeline.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
e = fixture.e


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'.local/synthetic-demo')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists(): raise SystemExit('Choose a fresh demo output directory.')
    output.mkdir(parents=True)
    store = output/'profiles'
    e.profiles.create(store, 'synthetic', 'SYNTHETIC FONT FIXTURE - not a person')
    template = output/'sampling.pdf'
    e.make_template(template)
    scans = fixture.filled_sheet(template.with_suffix('.json'), template, output/'filled.png',
                                 angle=90, perspective=True)
    imported = e.extract(store, 'synthetic', template.with_suffix('.json'), scans)
    if imported['missing']:
        raise SystemExit('Fixture extraction has missing glyphs: ' + repr(imported['missing']))
    # This automation accepts only its own labelled synthetic fixture.
    # Real user samples must be visually reviewed before review --accept.
    e.review(store, 'synthetic', True)
    content = {'blocks': [
        {'type':'heading', 'text':'Synthetic pipeline test'},
        {'type':'paragraph', 'text':'These glyphs were extracted from a computer-filled sampling sheet. This is not an imitation of any person.'},
        {'type':'paragraph', 'text':'ABC abc 0123456789. Revenue = 240 × 85 = ¥20,400. ROIC = 2.7 ÷ 24 = 11.25%.'},
        {'type':'paragraph', 'runs':[{'text':'C'}, {'text':'1','subscript':True}, {'text':' = 60 ÷ 6 = 10; x'},
                                    {'text':'2','superscript':True}, {'text':' + 3 = 7. π = 3.14; Δ = 0.5.'}]},
        {'type':'paragraph', 'text':'Letters, digits and symbols share the same captured glyph library.'}
    ]}
    source = output/'document.json'
    source.write_text(json.dumps(content,ensure_ascii=False,indent=2),encoding='utf-8')
    rendered = e.render(store, 'synthetic', source, output/'result.pdf', seed=42)
    validated = e.validate_output(rendered['report'], output/'rendered')
    print(json.dumps({'fixture':'synthetic-font-only','extraction':imported,
                      'render':rendered,'validation':validated},ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
