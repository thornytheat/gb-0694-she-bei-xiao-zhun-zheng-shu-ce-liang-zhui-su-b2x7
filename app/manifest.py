import hashlib, time
from app.config import RULE_VERSION, DECLARATION_COVERAGE_K
def make(text):
    digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
    return {'run_id':hashlib.sha256((RULE_VERSION+':'+digest).encode('utf-8')).hexdigest()[:16], 'sha256':digest, 'rule_version':RULE_VERSION, 'parameters':{'包含因子k':DECLARATION_COVERAGE_K,'不确定度合成':'路径去重后RSS，共享上级按共同系统分量保留'}, 'created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
