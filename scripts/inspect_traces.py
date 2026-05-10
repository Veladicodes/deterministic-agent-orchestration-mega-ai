import json, pathlib
p=pathlib.Path('results')
dirs=[d for d in p.iterdir() if d.is_dir()]
dirs=sorted(dirs,key=lambda d:d.stat().st_mtime,reverse=True)
run=dirs[0]
print('run',run.name)
traces=run/'traces.jsonl'
sel_counts={}
has_routing=0
total=0
skipped_agents=0
retries_count=0
tool_calls_count=0
actions_count={}
for line in open(traces,encoding='utf8'):
    if not line.strip(): continue
    total+=1
    t=json.loads(line)
    ep=t.get('execution_path',{})
    rds=ep.get('routing_decisions') or []
    if rds:
        has_routing+=1
        for d in rds:
            actions_count[d.get('selected_action')]=actions_count.get(d.get('selected_action'),0)+1
            if d.get('selected_action','').startswith('skip_'):
                skipped_agents+=1
    for ev in ep.get('agent_events',[]):
        retries_count+=ev.get('retries',0)
        tool_calls_count+=ev.get('tool_calls',0)

print('total_traces',total)
print('traces_with_routing',has_routing)
print('actions_count',actions_count)
print('skipped_agents_total',skipped_agents)
print('total_retries',retries_count)
print('total_tool_calls',tool_calls_count)
