"""Metadata review order only. Never grants identity, readiness, or execution."""
import json
from pathlib import Path
import re

PURPOSES = [
    {'id': 'tts', 'label': '음성 생성'},
    {'id': 'stt', 'label': '음성 인식·전사'},
    {'id': 'image', 'label': '이미지 생성 · 편집 미확인'},
    {'id': 'llm', 'label': '텍스트 대화'},
    {'id': 'tracking', 'label': '영상의 지정 지점 추적'},
]
RECIPES = (
    ('model_manifest.json', 'tts'), ('model_manifest_1.7b.json', 'tts'),
    ('adapter_manifest_whisper.json', 'stt'), ('adapter_manifest_image.json', 'image'),
    ('adapter_manifest_llama.json', 'llm'), ('adapter_manifest_tracking.json', 'tracking'),
)
WEIGHTS = {'.safetensors', '.bin', '.pt', '.pth', '.ckpt', '.gguf', '.onnx'}
CONFIGS = {'config.json', 'model_index.json', 'preprocessor_config.json', 'processor_config.json'}
NAMESPACED_PUBLISHERS = {'Qwen', 'openai', 'meta-llama', 'google'}
REASONS = {
    'choose_purpose': '하고 싶은 작업을 먼저 선택하세요. 전체 후보에 임의 순위를 부여하지 않습니다.',
    'purpose_match': '선택한 작업과 고정 프로필의 작업 종류가 같습니다. 후보의 실제 식별은 미확인입니다.',
    'purpose_hint': '이름·경로에 선택한 작업과 관련된 단서만 있습니다.',
    'purpose_mismatch': '선택한 작업과 일치하는 근거를 관찰하지 못했습니다.',
    'ambiguous_profile': '여러 고정 프로필 이름이 겹쳐 하나의 모델 후보로 판단할 수 없습니다.',
    'profile_unconfirmed': '고정 프로필의 명확한 이름 후보를 찾지 못했습니다. 현재 자동 검수 지원은 미확인입니다.',
    'unrecognized_name_form': '프로필과 비슷한 이름이 있지만 공식 게시자·전체 이름 경계가 일치하지 않아 이름 후보로 확정하지 않았습니다.',
    'profile_name_only': '고정 프로필 이름 후보입니다. 이름만으로 모델·revision·지원 상태를 확정하지 않습니다.',
    'not_model_root': '모델 root 후보가 아닌 구성요소/하위 폴더여서 별도 모델 추천번호를 주지 않습니다.',
    'no_primary_weight': '프로필의 주 가중치 이름·크기 metadata를 모두 관찰하지 못했습니다.',
    'config_not_observed': '프로필의 root 구성 파일 이름·크기 metadata를 모두 관찰하지 못했습니다.',
    'incomplete_scan': '부분·취소·중단 수집 기록이므로 번호 없이 확인 필요 후보로 표시합니다.',
    'shards_missing': '관찰한 shard 묶음 안에 빠진 조각이 있어 번호를 부여하지 않습니다.',
    'metadata_observed': '고정 프로필이 요구하는 모델 기준 폴더 파일의 이름·크기 정보와 완료 수집 기록을 관찰했습니다.',
    'file_evidence_only': '파일은 모델 단위가 아닙니다. 파일에는 관련성 근거만 표시하며, 모델 추천번호는 후보 그룹에서 확인하세요.',
    'component_only': '구성 파일·배포 문서만으로 독립 모델 추천번호를 만들지 않습니다.',
    'catalog_unavailable': '고정 프로필 기준을 읽지 못해 추천번호를 부여하지 않습니다.',
    'duplicate_names': '같은 후보 그룹 안에 중복 파일명이 있어 어느 구성인지 확정할 수 없습니다.',
    'distributed_weights_unobserved': '이미지 관련 구성 후보는 있지만 서로 다른 폴더의 분산 가중치를 안전하게 연결하지 못해 순위를 보류합니다. 모델이 없다는 뜻은 아닙니다.',
}
LIMITATIONS = [
    '현재 작업실의 선택된 Drive 수집 파일 metadata 기준입니다. 로컬·외장 폴더를 자동 탐색한 결과가 아닙니다.',
    '추천은 검토 우선순위이며 실측 성능·품질·성공 확률 순위가 아닙니다.',
    '모델/revision 식별·전체 필수 파일·전체 SHA·현재 runtime·자원·실추론·품질은 미확인입니다.',
    'shard 누락 0은 관찰된 묶음 안의 값이며 전체 가중치 완전성 증명이 아닙니다.',
]


def policy(purpose, view):
    return dict(version=2, purpose=purpose, purposes=PURPOSES,
                source='current_workspace_drive_inventory_metadata',
                unit='candidate_groups' if view == 'models' else 'file_relevance_only',
                criteria=[REASONS[k] for k in ('purpose_match', 'profile_name_only', 'metadata_observed')],
                rank_requirements=['목적 일치', '단일 고정 프로필 이름 후보', '모델 기준 폴더에서 프로필이 요구하는 파일의 이름·크기 관찰', '완료 수집', '관찰 shard 누락 없음'],
                tie_break='동일 근거는 이름·계정·ID로 고정 정렬합니다. 용량·파라미터 수·파일 수로 품질을 추정하지 않습니다.',
                limitations=LIMITATIONS + (['현재 고정 이미지 프로필은 이미지 생성용입니다. 이미지 편집 지원을 확인하지 않았습니다.'] if purpose == 'image' else []))


def _profiles(catalog=None):
    result=[]
    catalog = catalog if catalog is not None else [(json.loads(Path(__file__).with_name(filename).read_text(encoding='utf8')), purpose) for filename, purpose in RECIPES]
    for value, purpose in catalog:
        assert value['model_id'] and value['files']
        aliases={value['model_id'].casefold(), value['name'].rsplit('/', 1)[-1].casefold()}
        if value['model_id']=='tapir':aliases.add('tapnet')
        publisher, separator, canonical = value['name'].rpartition('/')
        # Explicitly scoped to publishers in the fixed manifests. Never strip an arbitrary
        # publisher prefix, suffix, or a partial model name from an observed folder.
        namespaced = {publisher.casefold()+join+canonical.casefold() for join in ('--','__')} if separator and publisher in NAMESPACED_PUBLISHERS else set()
        result.append(dict(value, purpose=purpose, aliases=aliases, namespaced_aliases=namespaced))
    return result


def _name_form(value, profile):
    value=value.casefold()
    if value in profile['aliases']:return 'canonical'
    if value in profile.get('namespaced_aliases',set()):return 'official_namespace'
    return None


def _unrecognized_names(row, profiles):
    # Diagnostic only. These lookalikes never enter _hints or grant a root match.
    values=re.split(r'[/\\]',row['path'])
    result=[]
    for value in values:
        folded=value.casefold()
        for p in profiles:
            if _name_form(value,p):continue
            if any(folded.endswith(join+alias) or folded.startswith(alias+join) for alias in p['aliases'] for join in ('--','__')):
                result.append(value);break
    return result


def _hints(row, profiles):
    segments={p.casefold() for p in re.split(r'[/\\]', row['path']) if p}
    files=row.get('files') or [row]
    # A unique fixed checkpoint filename is a name hint, never a verified model ID.
    unique={}
    for profile in profiles:
        for f in profile['files']:
            if '/' not in f['path'] and Path(f['path']).suffix in WEIGHTS:
                unique.setdefault(f['path'].casefold(),set()).add(profile['model_id'])
    names={f['name'].casefold() for f in files if f['kind']=='weight_candidate'}
    return [p for p in profiles if any(_name_form(segment,p) for segment in segments) or any(len(ids)==1 and p['model_id'] in ids and name in names for name,ids in unique.items())]


def _task_clues(row, purpose):
    patterns={'tts':r'(?<![a-z0-9])(tts|kokoro|vibevoice)(?![a-z0-9])',
              'stt':r'(?<![a-z0-9])(whisper|asr)(?![a-z0-9])',
              'image':r'(?<![a-z0-9])(image|flux|stable.diffusion)(?![a-z0-9])',
              'llm':r'(?<![a-z0-9])(llama|bert|instruct)(?![a-z0-9])',
              'tracking':r'(?<![a-z0-9])(tapir|bootstapir|tapnet)(?![a-z0-9])'}
    return list(dict.fromkeys(value for value in re.split(r'[/\\]',row['path']) if purpose and re.search(patterns[purpose],value.casefold())))


def explain(row, purpose='', view='models', profiles=None):
    if purpose not in {'', *(p['id'] for p in PURPOSES)}:raise ValueError('invalid purpose')
    result=dict(purpose=purpose, rank=None, eligible=False, related=False, profile_name_candidates=[],
                identity='unverified', execution='unverified', quality='unassessed', reasons=[], limitations=list(LIMITATIONS),
                observed_name=row['name'], name_evidence=[], missing_evidence=[], task_clues=[], defined_profiles=[])
    codes=[]
    if not purpose:codes=['choose_purpose'];result['status']='purpose_unselected'
    else:
        try:
            profiles=_profiles() if profiles is None else profiles
            if not profiles:raise ValueError('catalog unavailable')
            hints=_hints(row,profiles)
        except (OSError,ValueError,KeyError,TypeError,AssertionError):
            hints=[];codes.append('catalog_unavailable')
        result['profile_name_candidates']=[dict(id=p['model_id'],purpose=p['purpose']) for p in hints]
        result['task_clues']=_task_clues(row,purpose)
        result['defined_profiles']=[p['name'].rsplit('/',1)[-1] for p in (profiles or []) if p['purpose']==purpose]
        unrecognized=_unrecognized_names(row,profiles) if profiles else []
        if unrecognized:codes.append('unrecognized_name_form')
        for p in hints:
            for segment in re.split(r'[/\\]',row['path']):
                form=_name_form(segment,p)
                if form:
                    result['name_evidence'].append(dict(observed=segment, profile=p['model_id'], form=form))
        result['related']=any(p['purpose']==purpose for p in hints) or bool(result['task_clues'])
        if len(hints)>1:codes.append('ambiguous_profile')
        elif not hints:codes.append('profile_unconfirmed')
        elif hints[0]['purpose']!=purpose:codes.append('purpose_mismatch')
        else:
            profile=hints[0];codes += ['purpose_match','profile_name_only']
            files=row.get('files') or [row]
            actual={f['name'].casefold():f for f in files}
            if len(actual)!=len(files):codes.append('duplicate_names')
            primary=[f for f in profile['files'] if '/' not in f['path'] and Path(f['path']).suffix in WEIGHTS]
            config=[f for f in profile['files'] if f['path'] in CONFIGS]
            def observed(expected):
                return all(f['path'].casefold() in actual and actual[f['path'].casefold()].get('size')==f['size'] for f in expected)
            root=bool(_name_form(row['name'],profile)) or (len(profile['files'])==1 and bool(primary) and observed(primary))
            if view=='files':codes.append('file_evidence_only')
            elif not root:codes.append('not_model_root')
            if not any(f['kind']=='weight_candidate' for f in files):codes.append('component_only')
            if not primary and profile['purpose']=='image':codes.append('distributed_weights_unobserved')
            elif not primary or not observed(primary):codes.append('no_primary_weight')
            if not observed(config):codes.append('config_not_observed')
            result['missing_evidence']=[dict(name=f['path'],status='missing' if f['path'].casefold() not in actual else 'size_mismatch') for f in primary+config if not observed([f])]
            if row['scan_status']!='complete':codes.append('incomplete_scan')
            if (row.get('observations') or {}).get('shards_missing',0):codes.append('shards_missing')
            result['eligible']=view=='models' and codes==['purpose_match','profile_name_only']
            if result['eligible']:codes.append('metadata_observed')
        if not result['related'] and 'purpose_mismatch' not in codes:codes.append('purpose_mismatch')
        elif result['related'] and 'purpose_match' not in codes:codes.append('purpose_hint')
        result['status']='review_recommended' if result['eligible'] else 'related_needs_review' if result['related'] else 'not_recommended'
    result['reason_codes']=codes
    result['reasons']=[REASONS[c] for c in codes]
    if 'profile_unconfirmed' in codes:
        result['reasons'][codes.index('profile_unconfirmed')]=f"관찰 이름 ‘{row['name']}’에 대응하는 고정 검수 프로필을 확인하지 못했습니다. 같은 계열의 다른 모델·변형을 지원한다는 뜻은 아닙니다."
    if 'unrecognized_name_form' in codes:
        result['reasons'][codes.index('unrecognized_name_form')]=f"이름 형태 ‘{' · '.join(unrecognized)}’의 게시자·전체 별칭이 허용 목록과 일치하지 않습니다. 임의 접두사를 제거해 추천하지 않습니다."
    if 'purpose_hint' in codes:
        result['reasons'][codes.index('purpose_hint')]=f"‘{row['name']}’ 그룹의 이름·경로에 선택한 작업 관련 단서만 있습니다. 모델 식별이나 실행 성공 근거는 아닙니다."
    if result['missing_evidence']:
        missing=' · '.join(f"{item['name']} ({'이름 미관찰' if item['status']=='missing' else '크기 불일치'})" for item in result['missing_evidence'])
        for code in ('no_primary_weight','config_not_observed'):
            if code in codes:result['reasons'][codes.index(code)] += ' 이 그룹의 부족 근거: '+missing+'.'
    if purpose=='image':result['limitations'].append('현재 고정 프로필은 이미지 생성용이며 편집 지원은 미확인입니다.')
    return result


def stable_key(row):
    return (row['name'].casefold(), row['account'], row['id'])


def annotate_and_rank(rows, purpose='', view='models', profiles=None):
    if profiles is None:
        try:profiles=_profiles()
        except (OSError,ValueError,KeyError,TypeError,AssertionError):profiles=[]
    enriched=[dict(row,recommendation=explain(row,purpose,view,profiles)) for row in rows]
    ordered=sorted(enriched,key=lambda row:(not row['recommendation']['eligible'],not row['recommendation']['related'],*stable_key(row)))
    rank=0
    for row in ordered:
        if row['recommendation']['eligible']:
            rank+=1;row['recommendation']['rank']=rank
    return enriched, ordered, rank
