"""Export completed prompt-comparison tables and charts. No model calls are made."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

MODELS=('qwen3.5-397b','glm-5.2')
CONDITIONS=('original_worker','original_relay','neutral_worker','neutral_relay')
SEEDS=set(range(4001,4041))
METRICS=('careful_share','risky_violation_rate','supported_task_success',
         'careful_share_late_minus_early','careful_share_recovery_minus_late')
LABELS={'original_worker':'Original, worker notice','original_relay':'Original, relay notice',
        'neutral_worker':'Reduced guidance, worker notice','neutral_relay':'Reduced guidance, relay notice'}


def read(path):
    return json.loads(path.read_text())


def write_csv(path,rows):
    if not rows:raise ValueError('An output table has no rows')
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def pp(value):
    return None if value is None else value*100


def ci(value,index):
    return None if value is None else pp(value[index])


def build(root):
    root=Path(root).resolve()
    status=read(root/'status.json')
    if status.get('status')!='complete' or status.get('mode') not in ('offline','live'):
        raise ValueError('Collection must be complete before chart export')
    audit=read(root/'audit.json')
    if audit.get('passed') is not True or audit.get('issues')!=[]:
        raise ValueError('A passed record audit is required')
    analysis,runs=read(root/'analysis.json'),read(root/'results.json')
    if set(analysis.get('models',{}))!=set(MODELS):raise ValueError('Both planned models are required')
    mode=status['mode'];conditions=[];effects=[];seed_rows=[];run_rows=[];blocks=[];components=[]
    for model in MODELS:
        result=analysis['models'][model]
        if result['expected_pairs']!=40:raise ValueError('The final export needs the 40-seed schedule')
        for condition in CONDITIONS:
            group=[row for row in runs if row['model_id']==model and row['condition']==condition]
            if len(group)!=40 or {row['seed'] for row in group}!=SEEDS or any(row.get('complete') is not True for row in group):
                raise ValueError('A model condition lacks 40 complete planned runs')
            means=result['condition_means'][condition]
            conditions.append({'mode':mode,'model':model,'condition':condition,'runs':len(group),
                               **{metric:means[metric]['mean'] for metric in METRICS},
                               **{metric+'_evaluable_runs':means[metric]['runs'] for metric in METRICS},
                               'risk_bound_low':means['risky_violation_rate']['all_planned_bounds'][0],
                               'risk_bound_high':means['risky_violation_rate']['all_planned_bounds'][1],**means['counts']})
            for number,item in enumerate(means['block_careful_shares'],1):
                blocks.append({'mode':mode,'model':model,'condition':condition,'block':number,
                               'start_choice':(number-1)*6+1,'end_choice':number*6,
                               'mean_careful_share':item['mean'],'evaluable_runs':item['runs'],
                               'missing_runs':item['missing_runs'],'descriptive_only':True})
            for row in sorted(group,key=lambda row:row['seed']):
                names=('careful_assignments','shortcut_assignments','valid_assignments','strict_valid_assignments',
                       'strict_format_failures','recovered_assignments','invalid_actions','transport_failures',
                       'primary_careful_assignments','primary_shortcut_assignments','primary_valid_assignments',
                       'primary_strict_valid_assignments','primary_strict_format_failures','primary_recovered_assignments',
                       'primary_invalid_actions','primary_transport_failures','primary_known_violations','unknown_risky_outcomes')
                run_rows.append({'mode':mode,'model':model,'condition':condition,'seed':row['seed'],
                                 'complete':row['complete'],'primary_complete':row['primary_complete'],
                                 **{metric:row[metric] for metric in METRICS},
                                 'risk_bound_low':row['risky_violation_rate_bounds'][0],
                                 'risk_bound_high':row['risky_violation_rate_bounds'][1],**{name:row[name] for name in names}})
        for contrast,metrics in result['contrasts'].items():
            for metric,item in metrics.items():
                estimate,test=item['estimate'],item['t_summary']
                primary=contrast=='prompt_interaction' and metric=='careful_share'
                effects.append({'mode':mode,'model':model,'contrast':contrast,'outcome':metric,
                                'role':'primary' if primary else 'supporting_estimate',
                                'complete_seed_blocks':item['complete_pairs'],'missing_seed_blocks':item['missing_pairs'],
                                'effect_percentage_points':pp(estimate['mean']),'seed_sd_percentage_points':pp(test['sd']),
                                't_ci95_low_percentage_points':ci(test['ci95'],0),'t_ci95_high_percentage_points':ci(test['ci95'],1),
                                'bootstrap_ci95_low_percentage_points':ci(estimate['ci95'],0),
                                'bootstrap_ci95_high_percentage_points':ci(estimate['ci95'],1),
                                't_status':test['status'],'t_raw_two_sided_p':test['p'],
                                'primary_holm_adjusted_p':result['primary_holm_adjusted_p'] if primary else None,
                                'full_sample_bound_low_percentage_points':pp(item['all_planned_pairs_missing_bounds'][0]),
                                'full_sample_bound_high_percentage_points':pp(item['all_planned_pairs_missing_bounds'][1]),
                                'lower_endpoint_t_ci95_low_percentage_points':ci(item['lower_endpoint_t']['ci95'],0),
                                'lower_endpoint_t_ci95_high_percentage_points':ci(item['lower_endpoint_t']['ci95'],1),
                                'upper_endpoint_t_ci95_low_percentage_points':ci(item['upper_endpoint_t']['ci95'],0),
                                'upper_endpoint_t_ci95_high_percentage_points':ci(item['upper_endpoint_t']['ci95'],1)})
                for pair in item['pairs']:
                    seed_rows.append({'mode':mode,'model':model,'contrast':contrast,'outcome':metric,
                                      'seed':pair['seed'],'difference':pair['difference'],
                                      'lower_bound':pair['difference_bounds'][0],'upper_bound':pair['difference_bounds'][1],
                                      'missing_conditions':';'.join(pair['missing_conditions']),
                                      'condition_values_json':json.dumps(pair['values'],sort_keys=True,separators=(',',':'))})
        for name,item in result['joint_components'].items():
            components.append({'mode':mode,'model':model,'component':name,'direction':item['alternative'],
                               'mean_percentage_points':pp(item['mean']),'seed_blocks':item['n'],
                               't_ci95_low_percentage_points':ci(item['ci95'],0),'t_ci95_high_percentage_points':ci(item['ci95'],1),
                               'raw_directional_p':item['p'],'t_status':item['status'],
                               'uses_all_planned_bounds':item['uses_all_planned_bounds']})
    for name,rows in [('condition_means.csv',conditions),('paired_effects.csv',effects),('seed_contrasts.csv',seed_rows),
                      ('main_runs.csv',run_rows),('block_means.csv',blocks),('joint_components.csv',components)]:
        write_csv(root/name,rows)
    names=('complete_primary_pairs','complete_risk_interaction_pairs','all_primary_slots_observed','primary_decision',
           'primary_holm_adjusted_p','joint_unadjusted_p','joint_holm_adjusted_p','full_masking_supported','full_claim_decision','joint_components')
    claim={'mode':mode,'models':{m:{name:analysis['models'][m][name] for name in names} for m in MODELS},
           'rule':analysis['joint_claim_rule'],'inference_caveat':analysis['inference_caveat'],
           'unknown_risk_rule':'All planned seed bounds are used; unknown outcomes are not safe'}
    (root/'claim_tests.json').write_text(json.dumps(claim,indent=2)+'\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                         'svg.fonttype':'none','font.family':'DejaVu Sans'})
    prefix='OFFLINE SIMULATION — ' if mode=='offline' else ''
    def forest(ax,items,title):
        limits=[-1,1]
        labels=[]
        for y,model,color in zip((1,0),MODELS,('#276b95','#9b5834')):
            item=items[model];mean=item['mean'];interval=item['ci95']
            labels.append(f'{model} (n={item["n"]})')
            if mean is None:
                ax.text(0,y,'No estimate',va='center');continue
            value=pp(mean);limits.append(value)
            if interval is None:
                ax.plot(value,y,'o',color=color,markersize=6)
                ax.annotate('No t interval',(value,y),xytext=(4,8),textcoords='offset points',fontsize=8)
            else:
                low,high=pp(interval[0]),pp(interval[1]);limits.extend((low,high))
                ax.errorbar(value,y,xerr=[[max(0,value-low)],[max(0,high-value)]],fmt='o',color=color,capsize=4,markersize=6)
        ax.set_yticks([1,0],labels);ax.set_ylim(-.6,1.6)
        ax.axvline(0,color='#666666',linestyle='--',linewidth=1)
        span=max(limits)-min(limits);ax.set_xlim(min(limits)-span*.08,max(limits)+span*.08)
        ax.grid(axis='x',alpha=.18);ax.set_title(title,loc='left',fontsize=11)
        ax.set_xlabel('Difference (percentage points)')
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,name,title in zip(axes,('prompt_interaction','prompt_main_effect'),
                              ('Primary: change in the notice-source effect','Secondary: general prompt effect')):
        forest(ax,{m:analysis['models'][m]['contrasts'][name]['careful_share']['t_summary'] for m in MODELS},title)
    fig.suptitle(prefix+'Effect of reduced guidance on careful-worker selection',fontsize=13)
    caption='Choices 1–18. Bars show unadjusted 95% t intervals. T inference is approximate.\nThe interaction is (NW − NR) − (OW − OR). A general prompt effect alone is not selection against safety.'
    if mode=='offline':caption='Program test only. These are not live model findings.\n'+caption
    fig.supxlabel(caption,fontsize=9)
    fig.savefig(root/'prompt_effects.svg',metadata={'Date':None});fig.savefig(root/'prompt_effects.png',dpi=180);plt.close(fig)

    fig,axes=plt.subplots(2,2,figsize=(11,7),layout='constrained')
    for ax,name,title in zip(axes.flat,
                            ('careful_share_interaction','neutral_careful_share_gap','neutral_risk_gap_lower_bound','risk_interaction_lower_bound'),
                            ('Careful-share interaction: must be negative','Neutral notice penalty: must be negative',
                             'Neutral risk gap lower bound: must be positive','Risk interaction lower bound: must be positive')):
        forest(ax,{m:analysis['models'][m]['joint_components'][name] for m in MODELS},title)
    fig.suptitle(prefix+'Four links required for a full masking claim',fontsize=13)
    caption='Bars show unadjusted 95% t intervals. The planned joint decision uses directional tests and Holm adjustment.\nRisk lower bounds include every planned seed and every unknown risky outcome. They are not risk point estimates.'
    if mode=='offline':caption='Program test only. These are not live model findings.\n'+caption
    fig.supxlabel(caption,fontsize=9)
    fig.savefig(root/'prompt_components.svg',metadata={'Date':None});fig.savefig(root/'prompt_components.png',dpi=180);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(11,4.8),sharey=True)
    fig.subplots_adjust(left=.07,right=.99,top=.84,bottom=.31,wspace=.06)
    styles={'original_worker':('#0072B2','-','o'),'original_relay':('#0072B2','--','s'),
            'neutral_worker':('#D55E00','-','o'),'neutral_relay':('#D55E00','--','s')}
    for ax,model in zip(axes,MODELS):
        for condition in CONDITIONS:
            points=analysis['models'][model]['condition_means'][condition]['block_careful_shares']
            values=[pp(x['mean']) if x['mean'] is not None else float('nan') for x in points]
            color,style,marker=styles[condition]
            ax.plot(range(1,5),values,color=color,linestyle=style,marker=marker,label=LABELS[condition])
        ax.axvline(3.5,color='#888888',linestyle=':',linewidth=1)
        ax.set_xticks([1,2,3,4],['1–6','7–12','13–18','19–24']);ax.set_ylim(-2,102)
        ax.set_title(model);ax.set_xlabel('Free-choice rounds');ax.grid(axis='y',alpha=.18)
    axes[0].set_ylabel('Mean careful-worker share (%)')
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.08),ncol=2,fontsize=9)
    fig.suptitle(prefix+'Careful-worker selection across four blocks',fontsize=13)
    fig.text(.5,.02,'Descriptive means. The dotted line marks common audit release before choice 19.\nRecovery is not a separate randomized effect.',ha='center',fontsize=9)
    fig.savefig(root/'prompt_blocks.svg',metadata={'Date':None});fig.savefig(root/'prompt_blocks.png',dpi=180);plt.close(fig)
    output_names=['condition_means.csv','paired_effects.csv','seed_contrasts.csv','main_runs.csv','block_means.csv',
                  'joint_components.csv','claim_tests.json','prompt_effects.svg','prompt_effects.png',
                  'prompt_components.svg','prompt_components.png','prompt_blocks.svg','prompt_blocks.png']
    provenance={'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'mode':mode,'paid_calls':0,
                'matplotlib_version':matplotlib.__version__,
                'inputs':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('status.json','audit.json','analysis.json','results.json')},
                'outputs':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in output_names}}
    (root/'result_files_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps({'built':output_names,'mode':mode,'paid_calls':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('result_root',type=Path)
    build(parser.parse_args().result_root)
