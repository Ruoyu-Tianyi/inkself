"""Fit an experimental local habit adapter from an already reviewed word/glyph bank."""
import argparse,json,hashlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from web.runtime.reference_renderer import load_bank
from web.runtime.habit_model import align_words,fit_habits

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--bank',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--exclude',action='append',default=[],help='Word withheld from all fitting; repeat to exclude several.')
 args=parser.parse_args();bank=load_bank(args.bank);alignment=align_words(bank)
 model=fit_habits(bank,alignment,excluded=set(args.exclude));model['bank_sha256']=hashlib.sha256(args.bank.read_bytes()).hexdigest()
 args.output.parent.mkdir(parents=True,exist_ok=True)
 args.output.write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'training_words':len(model['training_words']),'character_observations':model['observations'],
                   'connector_examples':model['connector_examples'],'learned_allographs':len(model['allographs']),
                   'excluded_words':model['excluded_words']},ensure_ascii=False))
if __name__=='__main__':main()
