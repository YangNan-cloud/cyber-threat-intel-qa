#!/usr/bin/env python3
"""
CTI 数据集实体/关系标注脚本（面向知识图谱构建）

 输入 : cti_200_dataset.jsonl  (CISA KEV Catalog CVE 记录 + MITRE ATT&CK APT/Technique 记录
        + ThreatFox IOC/Malware 记录)
 输出 :
   - annotated_dataset.jsonl   每条的 entities + relations + label(NER spans) + url + ioc
   - kg_nodes.csv / kg_edges.csv  全局去重后的知识图谱节点/边 (可直接导入 Neo4j)

实体类型:
  Vulnerability(CVE) / Vendor / Product / VulnerabilityClass(CWE) /
  ThreatActor(APT组织) / Software(恶意软件/工具) / Country / Sector / Campaign

 关系类型:
   affects / developed_by / has_class / chained_with / incomplete_patch_of /
   uses / attributed_to / targets / related_to / associated_with

 可选 LLM 补全(默认关闭): 设置环境变量 LLM_ENRICH=1 或命令行传 --llm,
 对 MITRE 记录补齐规则引擎漏掉的无 ID 软件(Software)与 TTP 手法(Technique),
 关系 uses(ThreatActor -> Software) 与 uses_technique(ThreatActor -> Technique)。
 详见 llm_enrich.py。

 方法: 规则抽取(模板解析 + 词表匹配), 全部确定可复现; LLM 补全为 llm_inference。
"""
import json
import os
import re
import sys
import csv
from collections import OrderedDict, defaultdict

# 是否启用 DeepSeek LLM 补全标注(需 DEEPSEEK_API_KEY 非空)
LLM_ENRICH = os.environ.get("LLM_ENRICH") == "1" or "--llm" in sys.argv

# ----------------------------------------------------------------------------
# 0. 工具函数
# ----------------------------------------------------------------------------

# norm() 仅用于"模式匹配", 与原文保持 1:1 字符长度, 因此偏移量可直接用于原文
def norm(text: str) -> str:
    return (text.replace("\u2011", "-").replace("\u2010", "-")
                .replace("\u2012", "-").replace("\u2013", "-").replace("\u2014", "-")
                .replace("\u2019", "'").replace("\u2018", "'"))


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def tolerant_pattern(needle: str) -> str:
    """把 needle 转成正则: 连字符容忍 Unicode 变体, 空白容忍多个."""
    parts = []
    for ch in needle:
        if ch.isspace():
            parts.append(r"\s+")
        elif ch in "-\u2011\u2010\u2012\u2013\u2014":
            parts.append(r"[-\u2011\u2010\u2012\u2013\u2014]")
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


def find_all_spans(text: str, needle: str, flags: int = 0):
    """在原文中找 needle 的所有出现位置 (容错连字符/空白). 返回 [(s,e), ...]"""
    pat = tolerant_pattern(needle)
    return [(m.start(), m.end()) for m in re.finditer(pat, text, flags)]


def dedup_spans(spans):
    return sorted(set(spans))


def sentence_spans(t):
    """按句号/问号/感叹号切句, 返回 [(start,end), ...]; 不把 "U.S." 等缩写误切."""
    ms = list(re.finditer(r"(?<=[.!?])\s+(?=[A-Z(\[])", t))
    spans = []
    prev = 0
    for m in ms:
        spans.append((prev, m.end()))
        prev = m.end()
    if prev < len(t):
        spans.append((prev, len(t)))
    return spans


def sentence_of(spans, pos):
    for s, e in spans:
        if s <= pos < e:
            return (s, e)
    return None


# ----------------------------------------------------------------------------
# 0b. IOC 与 url 抽取
# ----------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")


def extract_ioc(text: str) -> dict:
    """抽取 IOC(ips / domains / hashes)。

    先清洗 markdown 链接 URL 与 (Citation:...) 噪音, 避免把 attack.mitre.org
    之类的参考链接误判为威胁域名; 域名要求 TLD 为小写 2-4 位, 排除
    Ajax.NET / TEMP.Hermit 之类的非 IOC 词; IP 校验每个八位组 0-255。
    url 型 IOC(如 http://evil.example/x)由其主机名被域名/IP 正则自然捕获。
    """
    clean = _MD_LINK_RE.sub(r"\1", text)
    clean = re.sub(r"\(Citation:[^)]*\)", " ", clean)
    ips = [m for m in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", clean)
           if all(0 <= int(o) <= 255 for o in m.split("."))]
    domains = re.findall(r"\b(?:[a-zA-Z0-9-]+\.)+[a-z]{2,4}\b", clean)
    hashes = re.findall(r"\b[a-fA-F0-9]{32,64}\b", clean)
    return {"ips": sorted(set(ips)), "domains": sorted(set(domains)), "hashes": sorted(set(hashes))}


def extract_primary_url(text: str) -> str:
    """记录主来源链接: 首条 attack.mitre.org 链接; 无则空串(如 CVE 记录)."""
    m = re.search(r"https://attack\.mitre\.org/[^\s)\]]+", text)
    return m.group(0) if m else ""


class RecordAnnotator:
    def __init__(self, text):
        self.text = text
        self.ntext = norm(text)          # 匹配用
        self.entities = []
        self.relations = []
        self.warnings = []

    def add_entity(self, etype, name, attrs=None, spans=()):
        ent = {
            "id": f"e{len(self.entities) + 1}",
            "type": etype,
            "name": name,
            "attrs": attrs or {},
            "spans": dedup_spans(spans),
        }
        self.entities.append(ent)
        return ent

    def add_relation(self, head, rtype, tail, method="template"):
        self.relations.append({"head": head["id"], "type": rtype,
                               "tail": tail["id"], "method": method})


# ----------------------------------------------------------------------------
# 1. CVE (CISA KEV) 标注
# ----------------------------------------------------------------------------

CVE_RE = r"CVE[-\u2011\u2010\u2012\u2013]\d{4}[-\u2011\u2010\u2012\u2013]\d{4,7}"

# 'affects X.' 中的 X -> (Vendor, Product) 人工校对表 (collapse 后作 key)
VENDOR_PRODUCT = {
    "PaperCut NG/MF": ("PaperCut", "NG/MF"),
    "ownCloud ownCloud": ("ownCloud", "ownCloud"),
    "Linux Kernel": ("Linux", "Kernel"),
    "JFrog Artifactory": ("JFrog", "Artifactory"),
    "Red Hat Libuser": ("Red Hat", "Libuser"),
    "Red Hat Automatic Bug Reporting Tool": ("Red Hat", "Automatic Bug Reporting Tool"),
    "Citrix NetScaler ADC and NetScaler Gateway": ("Citrix", "NetScaler ADC and NetScaler Gateway"),
    "Microsoft SQL Server": ("Microsoft", "SQL Server"),
    "Gitea Gitea": ("Gitea", "Gitea"),
    "Oracle HTTP Server and Oracle Weblogic Server Proxy Plug-in": ("Oracle", "HTTP Server and Oracle Weblogic Server Proxy Plug-in"),
    "Synacor Zimbra Collaboration Suite (ZCS)": ("Synacor", "Zimbra Collaboration Suite (ZCS)"),
    "TrueConf Server": ("TrueConf", "Server"),
    "MLflow MLflow": ("MLflow", "MLflow"),
    "Microsoft Internet Key Exchange (IKE) Service Extensions": ("Microsoft", "Internet Key Exchange (IKE) Service Extensions"),
    "Broadcom VMware vCenter": ("Broadcom", "VMware vCenter"),
    "Microsoft SharePoint": ("Microsoft", "SharePoint"),
    "Apple macOS": ("Apple", "macOS"),
    "Ray-Project Ray": ("Ray-Project", "Ray"),
    "Cisco Secure Firewall Adaptive Security Appliance (ASA) and Secure Firewall Threat Defense (FTD)": ("Cisco", "Secure Firewall Adaptive Security Appliance (ASA) and Secure Firewall Threat Defense (FTD)"),
    "Microsoft Windows Ancillary Function Driver for WinSock": ("Microsoft", "Windows Ancillary Function Driver for WinSock"),
    "Metabase Metabase": ("Metabase", "Metabase"),
    "Progress LoadMaster": ("Progress", "LoadMaster"),
    "JetBrains TeamCity": ("JetBrains", "TeamCity"),
    "N-able N-central": ("N-able", "N-central"),
    "Apache Tomcat": ("Apache", "Tomcat"),
    "IBM Langflow": ("IBM", "Langflow"),
    "Cisco Secure Firewall Management Center (FMC)": ("Cisco", "Secure Firewall Management Center (FMC)"),
    "Fortinet FortiOS": ("Fortinet", "FortiOS"),
    "Arista VeloCloud Orchestrator": ("Arista", "VeloCloud Orchestrator"),
    "Check Point SmartConsole": ("Check Point", "SmartConsole"),
    "WordPress Core": ("WordPress", "Core"),
    "Langflow Langflow": ("Langflow", "Langflow"),
    "DD-WRT DD-WRT": ("DD-WRT", "DD-WRT"),
    "Fortinet FortiSandbox": ("Fortinet", "FortiSandbox"),
    "Oracle E-Business Suite": ("Oracle", "E-Business Suite"),
    "KNX Association KNX Protocol Connection Authorization Option 1": ("KNX Association", "KNX Protocol Connection Authorization Option 1"),
    "Microsoft Active Directory Federation Services": ("Microsoft", "Active Directory Federation Services"),
    "Microsoft SharePoint Server": ("Microsoft", "SharePoint Server"),
    "SonicWall SMA1000 Appliances": ("SonicWall", "SMA1000 Appliances"),
    "Cisco IOS": ("Cisco", "IOS"),
    "Balbooa Forms": ("Balbooa", "Forms"),
    "iCagenda iCagenda": ("iCagenda", "iCagenda"),
    "JoomShaper SP Page Builder": ("JoomShaper", "SP Page Builder"),
    "Joomlack Page Builder": ("Joomlack", "Page Builder"),
    "Adobe ColdFusion": ("Adobe", "ColdFusion"),
    "SimpleHelp SimpleHelp": ("SimpleHelp", "SimpleHelp"),
    "PTC Windchill and FlexPLM": ("PTC", "Windchill and FlexPLM"),
    "Cisco Unified Communications Manager": ("Cisco", "Unified Communications Manager"),
    "Lantronix EDS5000": ("Lantronix", "EDS5000"),
    "Ubiquiti UniFi OS": ("Ubiquiti", "UniFi OS"),
    "Splunk Enterprise": ("Splunk", "Enterprise"),
    "Widget Factory Joomla Content Editor": ("Widget Factory", "Joomla Content Editor"),
    "LiteSpeed cPanel Plugin": ("LiteSpeed", "cPanel Plugin"),
    "Cisco Catalyst SD-WAN Manager": ("Cisco", "Catalyst SD-WAN Manager"),
    "Oracle PeopleSoft Enterprise PeopleTools": ("Oracle", "PeopleSoft Enterprise PeopleTools"),
    "Ivanti Sentry": ("Ivanti", "Sentry"),
    "Ajax.NET Professional Ajax.NET Professional": ("Ajax.NET Professional", "Ajax.NET Professional"),
}

# 漏洞类型 -> CWE 映射 (key 为小写, 去掉冠词)
CLASS_DISPLAY = {
    "os command injection": "OS Command Injection",
    "sql injection": "SQL Injection",
    "unix symbolic link (symlink) following": "UNIX Symbolic Link (Symlink) Following",
    "use-after-free": "Use-After-Free",
    "server-side request forgery (ssrf)": "Server-Side Request Forgery (SSRF)",
}
CWE_MAP = {
    "unsafe reflection": "CWE-470",
    "missing authentication for critical function": "CWE-306",
    "improper authentication": "CWE-287",
    "race condition": "CWE-362",
    "privilege escalation": "CWE-269",
    "out-of-bounds memory write": "CWE-787",
    "improper restriction of operations within the bounds of a memory buffer": "CWE-119",
    "code injection": "CWE-94",
    "improper access control": "CWE-284",
    "os command injection": "CWE-78",
    "server-side request forgery": "CWE-918",
    "double free": "CWE-415",
    "path traversal": "CWE-22",
    "weak authentication": "CWE-1390",
    "use-after-free": "CWE-416",
    "sql injection": "CWE-89",
    "command injection": "CWE-77",
    "deserialization of untrusted data": "CWE-502",
    "missing encryption of sensitive data": "CWE-311",
    "use of hard-coded password": "CWE-798",
    "exposure of sensitive information to an unauthorized actor": "CWE-200",
    "interpretation conflict": "CWE-436",
    "inclusion of functionality from untrusted control sphere": "CWE-829",
    "stack-based buffer overflow": "CWE-121",
    "improper privilege management": "CWE-269",
    "overly restrictive account lockout mechanism": "CWE-645",
    "insufficient granularity of access control": "CWE-1220",
    "unrestricted upload of file with dangerous type": "CWE-434",
    "authorization bypass through user-controlled key": "CWE-639",
    "authentication bypass": "CWE-287",
    "authentication bypass using an alternate path or channel": "CWE-288",
    "improper input validation": "CWE-20",
    "unix symbolic link (symlink) following": "CWE-61",
    "directory or path traversal": "CWE-22",
    "cross-site request forgery": "CWE-352",
    "improper limitation of a pathname to a restricted directory": "CWE-22",
}

IMPACT_RULES = [
    ("Remote Code Execution", [
        r"remote code execution", r"execute\s+(?:an\s+)?arbitrary\s+(code|java bytecode|script|os commands|commands|operating system commands)",
        r"execution of arbitrary operating system commands", r"execute unauthorized (code|commands)",
        r"execute code", r"code execution", r"run shell commands", r"full rce", r"\brce\b",
        r"php code", r"arbitrary file upload", r"command execution", r"conduct command injection",
    ]),
    ("Denial of Service", [r"denial of service", r"denial-of-service", r"\bdos\b", r"reload unexpectedly"]),
    ("Privilege Escalation", [r"privilege escalation", r"elevate (to root|privileges)", r"gain (privileged access|privileges)", r"privileged access", r"root privileges"]),
    ("Information Disclosure", [r"exposure of sensitive information", r"sensitive information", r"access sensitive data", r"read any data", r"steal stored credentials", r"stored credentials", r"response_status", r"metadata services"]),
    ("Authentication Bypass", [r"authentication bypass", r"bypass (a|the) (security feature|patch)", r"bypass of the", r"without valid credentials", r"without authentication", r"forged token", r"login token", r"fully authenticated technician session", r"bypass multi-factor"]),
    ("Arbitrary File Manipulation", [r"access, modify, or delete any file", r"write (data|files)", r"create or truncate arbitrary files", r"overwrite any file", r"corrupt the /etc/passwd", r"access files on the underlying", r"create a file", r"purge all devices"]),
    ("Unauthorized Access", [r"unauthorized (access|creation|modification)", r"complete access to all", r"administrator access", r"gain administrator", r"modify certain system configurations", r"manipulate system configuration", r"log in to an affected device", r"takeover of", r"account takeover", r"purge all devices", r"execute any flow", r"make unauthorized changes", r"access privileged internal functionality", r"compromise[s]? the confidentiality, integrity, and availability"]),
    ("Server-Side Request Forgery", [r"server-side request forgery", r"\bssrf\b"]),
]


def extract_impacts(sd: str):
    impacts = set()
    for label, pats in IMPACT_RULES:
        for p in pats:
            if re.search(p, sd, re.I):
                impacts.add(label)
                break
    return sorted(impacts)


def extract_attack_position(sd: str):
    tags = set()
    if re.search(r"unauthenticated|un-authenticated|unauthorized (?:remote )?attacker|remote unauthorized attacker|without authentication|without valid credentials|forged token|no signing-key", sd, re.I):
        tags.add("unauthenticated")
    elif re.search(r"(?<!un)authenticated|authorized attacker|with repository write access|low-privileged account|certain permissions", sd, re.I):
        tags.add("authenticated")
    if re.search(r"\bremote\b(?!-)", sd, re.I):
        tags.add("remote")
    if re.search(r"\blocal(?:ly| users)?\b", sd, re.I):
        tags.add("local")
    if re.search(r"network", sd, re.I):
        tags.add("network")
    return sorted(tags)


def annotate_cve(item):
    text = item["text"]
    a = RecordAnnotator(text)
    nt = a.ntext

    # CVE 名称可能含一层嵌套括号, 如 "(ZCS)" / "(IKE)" / "(ASA) ... (FTD)"
    hm = re.search(r"Vulnerability\s+(" + CVE_RE + r")\s*\(((?:[^()]|\([^()]*\))*)\)\s*affects\s+(.+?)\.\s*Short Description:", nt)
    if not hm:
        a.warnings.append("header parse failed")
        return a
    cve_id = hm.group(1)
    cve_name = collapse(hm.group(2))
    affects_raw = collapse(hm.group(3))

    sdm = re.search(r"Short Description:\s*(.*?)\s*Required Action:", nt, re.S)
    sd = sdm.group(1).strip() if sdm else ""
    ram = re.search(r"Required Action:\s*(.*)", nt, re.S)
    required_action = ram.group(1).strip() if ram else ""

    vp = VENDOR_PRODUCT.get(affects_raw)
    if vp is None:  # 兜底: 第一段为厂商, 其余为产品
        parts = affects_raw.split(" ", 1)
        vp = (parts[0], parts[1] if len(parts) > 1 else parts[0])
        a.warnings.append(f"vendor/product fallback for {affects_raw!r}")
    vendor, product = vp

    # --- 漏洞实体 ---
    vuln = a.add_entity(
        "Vulnerability", cve_id,
        attrs={
            "cve_id": cve_id,
            "year": int(cve_id.split("-")[1]),
            "cve_name": cve_name,
            "impacts": extract_impacts(sd),
            "attack_position": extract_attack_position(sd),
            "end_of_life": bool(re.search(r"end-of-life|end-of-service|eol|eos", sd, re.I)),
            "mentioned_only": False,
        },
        spans=find_all_spans(text, cve_id),
    )

    # --- 漏洞类型实体 (优先 SD 的 'contains X vulnerability', 否则用 CVE 名称回退) ---
    sd_class, name_class = None, None
    m = re.search(r"contain[s]?\s+(?:an?\s+)?(.+?)\s+vulnerab", sd, re.I)
    if m:
        sd_class = collapse(m.group(1)).lower()
    for prefix in (f"{vendor} {product}", product, vendor):
        if cve_name.lower().startswith(prefix.lower() + " "):
            name_class = cve_name[len(prefix):].strip()
            break
    if name_class:
        name_class = re.sub(r"\s*vulnerability$", "", name_class, flags=re.I).strip()
    if name_class == sd_class:
        name_class = None
    if sd_class and name_class:
        if CWE_MAP.get(sd_class):
            class_raw = sd_class
        elif CWE_MAP.get(name_class.lower()):
            class_raw = name_class
        else:
            class_raw = sd_class
    else:
        class_raw = sd_class or name_class
    if class_raw:
        key = class_raw.lower()
        display = CLASS_DISPLAY.get(key, class_raw.title())
        cwe = CWE_MAP.get(key)
        cls = a.add_entity(
            "VulnerabilityClass", display,
            attrs={"cwe_id": cwe} if cwe else {},
            spans=find_all_spans(text, class_raw, re.I),
        )
        a.add_relation(vuln, "has_class", cls)
    else:
        a.warnings.append("no vulnerability class found")

    # --- 厂商/产品实体 ---
    v_ent = a.add_entity("Vendor", vendor, spans=find_all_spans(text, vendor))
    p_ent = a.add_entity("Product", product, spans=find_all_spans(text, product))
    a.add_relation(vuln, "affects", p_ent)
    a.add_relation(p_ent, "developed_by", v_ent)

    # --- 关联 CVE (chained with / incomplete patch for) ---
    seen = {cve_id}
    for m2 in re.finditer(CVE_RE, nt):
        other = m2.group(0)
        if other in seen:
            continue
        seen.add(other)
        ctx = nt[max(0, m2.start() - 90):m2.start()]
        rel_type = "related_to"
        if "chained with" in ctx:
            rel_type = "chained_with"
        elif "incomplete patch for" in ctx:
            rel_type = "incomplete_patch_of"
        other_ent = a.add_entity(
            "Vulnerability", other,
            attrs={"cve_id": other, "year": int(other.split("-")[1]), "mentioned_only": True},
            spans=find_all_spans(text, other),
        )
        a.add_relation(vuln, rel_type, other_ent, method="explicit")

    return a


# ----------------------------------------------------------------------------
# 2. MITRE ATT&CK 标注
# ----------------------------------------------------------------------------

ATTRIB_PATTERNS = [  # (正则, 国家/None)  -- 在整段描述上扫描, 命中即为"归因"
    (r"north korean|north korea[-\u2013\u2014 ]?aligned|dprk|democratic people'?s republic of korea|reconnaissance general bureau", "North Korea"),
    (r"people'?s republic of china|china-based|china-nexus|china-linked|chinese ministry of state security|ministry of state security|tianjin state security|\bpla\b|people'?s liberation army|operat\w* out of china|originating (?:primarily )?in china|guandong province of china|\bchinese\b|\bprc\b", "China"),
    (r"russia-based|general staff main intelligence|\bgru\b|\bfsb\b|\brussian\b", "Russia"),
    (r"iran'?s ministry|\bmois\b|\biranian\b|iran-based", "Iran"),
    (r"pakistan-based|\bpakistani\b", "Pakistan"),
    (r"pro-indian|indian entity|india-based|suspected indian", "India"),
    (r"vietnam-based|\bvietnamese\b", "Vietnam"),
    (r"lebanon-based|\blebanese\b", "Lebanon"),
    (r"türkiye-linked", "Türkiye"),
    (r"south korean origins", "South Korea"),
    (r"spanish-speaking", None),  # 仅记录归因描述, 不定国家
]

# 目标国家/地区 (canonical -> 别名列表); 区域在前, 避免 "Asia" 误吃 "Southeast Asia"
COUNTRY_ALIASES = [
    ("Middle East", ["Middle East"]),
    ("Southeast Asia", ["Southeast Asia"]),
    ("Asia-Pacific", ["Asia-Pacific"]),
    ("Latin America", ["Latin America"]),
    ("North America", ["North America"]),
    ("Asia", ["Asia"]),
    ("Africa", ["Africa"]),
    ("Europe", ["Europe"]),
    ("Guam", ["Guam"]),
    ("United States", ["United States", "the US", "U.S.", "US"]),
    ("United Kingdom", ["United Kingdom", "the UK", "U.K.", "UK"]),
    ("United Arab Emirates", ["United Arab Emirates", "UAE"]),
    ("North Korea", ["North Korea"]),
    ("South Korea", ["South Korea", "South Korean"]),
    ("China", ["China"]),
    ("Japan", ["Japan"]),
    ("Russia", ["Russia"]),
    ("India", ["India", "Indian"]),
    ("Pakistan", ["Pakistan"]),
    ("Afghanistan", ["Afghanistan", "Afghani"]),
    ("Nepal", ["Nepal"]),
    ("Vietnam", ["Vietnam"]),
    ("Philippines", ["Philippines"]),
    ("Cambodia", ["Cambodia"]),
    ("Laos", ["Laos"]),
    ("Malaysia", ["Malaysia"]),
    ("Mozambique", ["Mozambique"]),
    ("Belgium", ["Belgium"]),
    ("Australia", ["Australia"]),
    ("Romania", ["Romania"]),
    ("Kuwait", ["Kuwait"]),
    ("Taiwan", ["Taiwan"]),
    ("Hong Kong", ["Hong Kong"]),
    ("Mongolia", ["Mongolia"]),
    ("Belarus", ["Belarus"]),
    ("Sweden", ["Sweden"]),
    ("Iran", ["Iran"]),
    ("Rwanda", ["Rwanda"]),
    ("Türkiye", ["Türkiye", "Turkey", "Turkish"]),
    ("Ukraine", ["Ukraine"]),
    ("Poland", ["Poland"]),
    ("Spain", ["Spain"]),
    ("Germany", ["Germany"]),
    ("France", ["France"]),
    ("Italy", ["Italy"]),
    ("Israel", ["Israel", "Israeli"]),
    ("Lebanon", ["Lebanon"]),
    ("Saudi Arabia", ["Saudi Arabia"]),
    ("Indonesia", ["Indonesia"]),
    ("Thailand", ["Thailand"]),
    ("Myanmar", ["Myanmar"]),
    ("Bangladesh", ["Bangladesh"]),
    ("Sri Lanka", ["Sri Lanka"]),
    ("Singapore", ["Singapore"]),
    ("South Africa", ["South Africa"]),
    ("Nigeria", ["Nigeria"]),
    ("Kenya", ["Kenya"]),
    ("Canada", ["Canada"]),
    ("Mexico", ["Mexico"]),
    ("Brazil", ["Brazil"]),
    ("Argentina", ["Argentina"]),
    ("Chile", ["Chile"]),
    ("Colombia", ["Colombia"]),
    ("Peru", ["Peru"]),
    ("Venezuela", ["Venezuela"]),
    ("Guatemala", ["Guatemala"]),
    ("Cuba", ["Cuba"]),
    ("Netherlands", ["Netherlands"]),
    ("Norway", ["Norway"]),
    ("Finland", ["Finland"]),
    ("Denmark", ["Denmark"]),
    ("Switzerland", ["Switzerland"]),
    ("Austria", ["Austria"]),
    ("Czechia", ["Czechia"]),
    ("Hungary", ["Hungary"]),
    ("Greece", ["Greece"]),
    ("Portugal", ["Portugal"]),
    ("Ireland", ["Ireland"]),
    ("New Zealand", ["New Zealand"]),
    ("Egypt", ["Egypt"]),
    ("Syria", ["Syria"]),
    ("Iraq", ["Iraq"]),
    ("Qatar", ["Qatar"]),
    ("Jordan", ["Jordan"]),
    ("Oman", ["Oman"]),
    ("Kazakhstan", ["Kazakhstan"]),
    ("Uzbekistan", ["Uzbekistan"]),
    ("Kyrgyzstan", ["Kyrgyzstan"]),
    ("Turkmenistan", ["Turkmenistan"]),
    ("Azerbaijan", ["Azerbaijan"]),
    ("Armenia", ["Armenia"]),
    ("Georgia", ["Georgia"]),
]

SECTOR_PATTERNS = [  # (label, pattern, case_sensitive)
    ("Government", r"government|public sector", False),
    ("Defense", r"defense|military", False),
    ("Financial", r"financial|banking|finance|banks|payment card|point of sale|\bpos\b|atms|swift|cryptocurrency", False),
    ("Healthcare", r"healthcare|health care|medical|hospitals|infectious disease", False),
    ("Telecommunications", r"telecommunication|telecom|internet service provider|\bisp\b", False),
    ("Energy", r"energy|oil and natural gas|oil and gas|power companies|utilities|nuclear", False),
    ("Education", r"education|academic|universities|higher education", False),
    ("Technology", r"technology|software|information technology", False),
    ("Technology", r"\bIT\b", True),
    ("Retail", r"retail", False),
    ("Hospitality", r"hospitality|hotels|casinos|casino", False),
    ("Manufacturing", r"manufacturing|supply chain manufacturers", False),
    ("Aviation", r"aviation", False),
    ("Aerospace", r"aerospace", False),
    ("Transportation", r"transportation|maritime|shipping|logistics", False),
    ("Media", r"media|journalists|news", False),
    ("Legal", r"law firms|legal", False),
    ("Mining", r"mining", False),
    ("NGO", r"non-governmental|non-profit|human rights|think tank", False),
    ("Critical Infrastructure", r"critical infrastructure|industrial control systems|operational technology|\bot assets\b", False),
    ("Managed Service Providers", r"managed service provider|\bmsp\b", False),
    ("Business Process Outsourcing", r"business process outsourcing|\bbpo\b", False),
    ("Customer Relationship Management", r"customer relationship management|\bcrm\b", False),
    ("Gaming", r"gaming|video game", False),
    ("Travel", r"travel|tourism", False),
    ("Pharmaceutical", r"pharmaceutical", False),
    ("Food and Beverage", r"food and beverage", False),
    ("Consulting", r"consulting", False),
    ("Cloud Services", r"cloud services|\bcloud\b", False),
    ("Diplomacy", r"diplomatic|foreign policy", False),
    ("Religious Institutions", r"religious institutions", False),
    ("Research", r"research entities|research institutions", False),
    ("Insurance", r"insurance", False),
]

TARGET_CUE = r"target\w*|victims?\b|against|attack\w*|focus\w*|emphasis|primarily in|in at least|compromise\w*|intrusions?\b"

MOTIVATION_RULES = [
    ("espionage", r"(cyber)?espionage|corporate espionage|intelligence collection"),
    ("financial", r"financially[- ]motivated|financial cyber|criminal|cybercriminal|cryptojacking|ransomware|profit|payment card|theft of cryptocurrency"),
    ("destructive", r"destructive|disruptive"),
    ("political", r"politically motivated|political organizations"),
]


def annotate_mitre(item):
    text = item["text"]
    a = RecordAnnotator(text)
    nt = a.ntext

    nm = re.search(r"Entity/Technique Name:\s*(.+?)\.\s*Description:", nt)
    if not nm:
        a.warnings.append("header parse failed")
        return a
    primary_name = collapse(nm.group(1))

    glinks = [(m.group(1), m.group(2), m.start() + 1, m.start() + 1 + len(m.group(1)))
              for m in re.finditer(r"\[([^\]]+)\]\(https://attack\.mitre\.org/groups/(G\d+)\)", nt)]
    slinks = [(m.group(1), m.group(2), m.start() + 1, m.start() + 1 + len(m.group(1)))
              for m in re.finditer(r"\[([^\]]+)\]\(https://attack\.mitre\.org/software/(S\d+)\)", nt)]

    # --- 主实体 (ThreatActor) ---
    primary_gid = None
    for name, gid, _, _ in glinks:
        if name.lower() == primary_name.lower():
            primary_gid = gid
            break

    first_seen = None
    ym = re.search(r"since at least[^0-9]*(\d{4})", nt)
    if not ym:
        ym = re.search(r"as early as\s+(\d{4})", nt)
    if ym:
        first_seen = int(ym.group(1))

    motivations = []
    for label, pat in MOTIVATION_RULES:
        if re.search(pat, nt, re.I):
            motivations.append(label)

    actor = a.add_entity(
        "ThreatActor", primary_name,
        attrs={
            "attck_id": primary_gid,
            "first_seen": first_seen,
            "motivations": motivations,
            "attribution_details": [],
        },
        spans=find_all_spans(text, primary_name),
    )
    if primary_gid is None:
        a.warnings.append(f"no ATT&CK id for primary entity {primary_name!r}")

    # --- 其他威胁组织 (description 内链接, 按 ATT&CK ID 去重) ---
    secondary = []
    seen_gids = set()
    for name, gid, s, e in glinks:
        if name.lower() == primary_name.lower() or gid in seen_gids:
            continue
        seen_gids.add(gid)
        ent = a.add_entity("ThreatActor", name, attrs={"attck_id": gid}, spans=[(s, e)])
        secondary.append(ent)

    # --- 软件 (description 内链接, 按 ATT&CK ID 去重) ---
    softwares = []
    seen_sids = set()
    for name, sid, s, e in slinks:
        if sid in seen_sids:
            continue
        seen_sids.add(sid)
        ent = a.add_entity("Software", name, attrs={"attck_id": sid}, spans=[(s, e)])
        softwares.append(ent)

    # --- 关系: related_to / uses / associated_with ---
    for ent in secondary:
        a.add_relation(actor, "related_to", ent, method="co-occurrence")
    for ent in softwares:
        a.add_relation(actor, "uses", ent, method="co-occurrence")
    for i in range(len(softwares)):
        for j in range(i + 1, len(softwares)):
            a.add_relation(softwares[i], "related_to", softwares[j], method="co-occurrence")

    # --- 归因国家 ---
    # 匹配文本去掉 URL 与 (Citation: ...) 噪音; 归因短语若出现在"谈论其他组织"的句子里则不计入
    nt_clean = re.sub(r"\(Citation:[^)]*\)", " ", re.sub(r"https?://\S+", " ", nt))
    sent_spans = sentence_spans(nt_clean)
    group_names = {name for name, *_ in glinks}

    def sentence_about_other_group(s, e):
        sent = nt_clean[s:e]
        for g in group_names:
            if g.lower() == primary_name.lower():
                continue
            if re.search(r"(?<![A-Za-z0-9@.])" + re.escape(g) + r"(?![A-Za-z0-9@.])", sent, re.I):
                return True
        return False

    attr_spans = []
    attr_countries = set()
    low_clean = nt_clean.lower()
    for pat, country in ATTRIB_PATTERNS:
        for m in re.finditer(pat, low_clean):
            sent = sentence_of(sent_spans, m.start())
            if sent is None:
                continue
            if sentence_about_other_group(*sent):
                continue
            attr_spans.append((m.start(), m.end()))
            if country:
                attr_countries.add(country)
                actor["attrs"]["attribution_details"].append(m.group(0))
    for country in sorted(attr_countries):
        cent = a.add_entity("Country", country, spans=find_all_spans(text, country, re.I))
        a.add_relation(actor, "attributed_to", cent, method="attribution_pattern")

    # --- 目标国家 (句子级语境 + 已消费区间/重叠区间跳过) ---
    target_countries = set()
    used_spans = list(attr_spans)
    for canonical, aliases in COUNTRY_ALIASES:
        for alias in aliases:
            pat = r"(?<![A-Za-z])" + tolerant_pattern(alias) + r"(?![A-Za-z])"
            for m in re.finditer(pat, nt_clean, re.I):
                if any(s <= m.start() < e or m.start() <= s < m.end() for s, e in used_spans):
                    continue
                after = nt_clean[m.end():m.end() + 40]
                if re.search(r"sanction|indictment|prosecut", after, re.I):
                    continue
                sent = sentence_of(sent_spans, m.start())
                if sent is None:
                    continue
                if re.search(TARGET_CUE, nt_clean[sent[0]:sent[1]], re.I):
                    target_countries.add(canonical)
                    used_spans.append((m.start(), m.end()))
    for country in sorted(target_countries):
        cent = a.add_entity("Country", country, spans=find_all_spans(text, country, re.I))
        a.add_relation(actor, "targets", cent, method="co-occurrence")

    # --- 目标行业 (句子级语境) ---
    sectors = set()
    for label, pat, cs in SECTOR_PATTERNS:
        flags = 0 if cs else re.I
        for m in re.finditer(pat, nt_clean, flags):
            sent = sentence_of(sent_spans, m.start())
            if sent is None:
                continue
            if re.search(TARGET_CUE, nt_clean[sent[0]:sent[1]], re.I):
                sectors.add(label)
                break
    for label in sorted(sectors):
        sent = a.add_entity("Sector", label, spans=find_all_spans(text, label, re.I))
        a.add_relation(actor, "targets", sent, method="co-occurrence")

    # --- 行动/战役 (Operation X, 名称可能带 markdown 链接; 保留 citation, 战役名常出现其中) ---
    nt_nocit = re.sub(r"https?://\S+", " ", nt)
    campaigns = OrderedDict()
    for m in re.finditer(r"Operation\s+\[?([A-Z][A-Za-z0-9'\-\u2013\u2014 ]+?)(?=\]|[,.;)\]\):]|$)", nt_nocit):
        name = m.group(1).strip().rstrip(".")
        # 去掉尾部的月份引用, 如 "Operation Layover September 2021"
        name = re.split(r"\s+(?:September|January|February|March|April|May|June|July|August|October|November|December)\b", name)[0].strip()
        if not name:
            continue
        if f"operation {name}".lower() == primary_name.lower():  # 记录本身名字就是 Operation X
            continue
        campaigns[name] = m.start()
    for cname in campaigns:
        full = "Operation " + cname
        cent = a.add_entity("Campaign", full, spans=find_all_spans(text, full))
        a.add_relation(actor, "associated_with", cent, method="explicit")

    # --- LLM 补全(可选): 补齐无 ID 软件与 TTP 手法 ---
    if LLM_ENRICH:
        try:
            from llm_enrich import enrich_mitre  # 延迟导入, 避免循环依赖
        except Exception as e:
            a.warnings.append(f"llm_enrich import failed: {e}")
        else:
            enrich_mitre(a, actor)

    return a


# ----------------------------------------------------------------------------
# 2b. IOC/Malware (ThreatFox) 标注
# ----------------------------------------------------------------------------

def annotate_ioc(item):
    """ThreatFox IOC 记录: 提取恶意软件名作为 Software 实体。

    IOC 值(domain / ip / url / hash)由记录级 extract_ioc 捕获, 不建实体。
    """
    text = item["text"]
    a = RecordAnnotator(text)
    m = re.search(r"Threat Malware\s+(.+?)\s+associated IOC detected", a.ntext)
    if not m:
        a.warnings.append("ioc header parse failed")
        return a
    malware = collapse(m.group(1))
    a.add_entity("Software", malware, attrs={"source": "ThreatFox"}, spans=find_all_spans(text, malware))
    return a


# ----------------------------------------------------------------------------
# 3. 主流程
# ----------------------------------------------------------------------------

def node_key(ent, software_alias=None):
    t, name, attrs = ent["type"], ent["name"], ent["attrs"]
    if t == "Vulnerability":
        return "CVE:" + attrs["cve_id"]
    if t == "ThreatActor":
        return f"ATT&CK:{attrs['attck_id']}" if attrs.get("attck_id") else ("GROUP:" + name.lower())
    if t == "Software":
        if attrs.get("attck_id"):
            return f"ATT&CK:{attrs['attck_id']}"
        sid = (software_alias or {}).get(name.lower())
        return f"ATT&CK:{sid}" if sid else ("SOFTWARE:" + name.lower())
    return f"{t.upper()}:{name.lower()}"


def build_kg(records):
    # MITRE 软件名 -> attck_id 别名表: 把 ThreatFox 同名软件并入 ATT&CK 节点, 避免同物两节点
    software_alias = {}
    for rec in records:
        for ent in rec["entities"]:
            if ent["type"] == "Software" and ent["attrs"].get("attck_id"):
                software_alias[ent["name"].lower()] = ent["attrs"]["attck_id"]

    nodes = OrderedDict()
    edges = OrderedDict()
    for rec in records:
        rid = rec["id"]
        key_of = {}
        for ent in rec["entities"]:
            key = node_key(ent, software_alias)
            key_of[ent["id"]] = key
            if key in nodes:
                node = nodes[key]
                node["record_ids"].add(rid)
                if node["label"] == "Vulnerability":
                    # 用"主记录"的实体覆盖"提及"实体
                    if ent["attrs"].get("mentioned_only") is False:
                        node["name"] = ent["name"]
                        node["attrs"] = dict(ent["attrs"])
                        node["primary_record"] = rid
            else:
                nodes[key] = {
                    "node_id": key, "label": ent["type"], "name": ent["name"],
                    "attrs": dict(ent["attrs"]),
                    "record_ids": {rid},
                    "primary_record": rid,
                }
        for rel in rec["relations"]:
            src = key_of.get(rel["head"])
            dst = key_of.get(rel["tail"])
            if src is None or dst is None:
                continue
            ek = (src, rel["type"], dst)
            if ek in edges:
                edges[ek]["record_ids"].add(rid)
            else:
                edges[ek] = {"source": src, "target": dst, "relation": rel["type"],
                             "method": rel["method"], "record_ids": {rid}}
    return nodes, edges


def main():
    with open("cti_200_dataset.jsonl", encoding="utf-8") as f:
        items = [json.loads(line) for line in f]

    records = []
    stats = defaultdict(int)
    rel_stats = defaultdict(int)
    warn_total = 0

    for item in items:
        if item["type"] == "CVE":
            a = annotate_cve(item)
        elif item["type"] == "IOC/Malware":
            a = annotate_ioc(item)
        else:
            a = annotate_mitre(item)

        rec = dict(item)
        rec["entities"] = a.entities
        rec["relations"] = a.relations
        rec["label"] = [[s, e, e2["type"]] for e2 in a.entities for s, e in e2["spans"]]
        rec["label"].sort()
        rec["required_action"] = ""
        if item["type"] == "CVE":
            ram = re.search(r"Required Action:\s*(.*)", a.ntext, re.S)
            rec["required_action"] = ram.group(1).strip() if ram else ""
            rec["directives"] = ["BOD 26-04"] if "BOD 26-04" in a.ntext else []
        rec["url"] = extract_primary_url(item["text"])
        rec["ioc"] = extract_ioc(item["text"])
        records.append(rec)

        for e2 in a.entities:
            stats[e2["type"]] += 1
        for r in a.relations:
            rel_stats[r["type"]] += 1
        warn_total += len(a.warnings)
        if a.warnings:
            print(f"[warn] id={item['id']:3d} {a.warnings}")

    with open("annotated_dataset.jsonl", "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    nodes, edges = build_kg(records)
    with open("kg_nodes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["node_id", "label", "name", "attrs", "record_ids"])
        for n in nodes.values():
            w.writerow([n["node_id"], n["label"], n["name"],
                        json.dumps(n["attrs"], ensure_ascii=False),
                        " ".join(str(x) for x in sorted(n["record_ids"]))])
    with open("kg_edges.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "relation", "target", "method", "record_ids"])
        for e in edges.values():
            w.writerow([e["source"], e["relation"], e["target"], e["method"],
                        " ".join(str(x) for x in sorted(e["record_ids"]))])

    print("\n===== 标注统计 =====")
    print(f"记录总数: {len(records)}  (CVE: {sum(1 for r in records if r['type']=='CVE')}, "
          f"APT/Technique: {sum(1 for r in records if r['type']=='APT/Technique')})")
    print(f"告警总数: {warn_total}")
    print("\n实体数量 (按类型):")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k:22s} {v}")
    print("\n关系数量 (按类型):")
    for k, v in sorted(rel_stats.items(), key=lambda x: -x[1]):
        print(f"  {k:22s} {v}")
    print(f"\n全局去重后节点数: {len(nodes)}")
    print(f"全局去重后边数: {len(edges)}")
    # 无标签实体检查
    empty = [r["id"] for r in records if not r["entities"]]
    if empty:
        print(f"!! 无实体记录: {empty}")
    # CVE 覆盖检查
    no_imp = [r["id"] for r in records if r["type"] == "CVE"
              and not any(e["type"] == "Vulnerability" and not e["attrs"].get("mentioned_only")
                          and e["attrs"].get("impacts") for e in r["entities"])]
    if no_imp:
        print(f"!! 无 impact 标签的 CVE 记录: {no_imp}")
    no_class = [r["id"] for r in records if r["type"] == "CVE"
                and not any(e["type"] == "VulnerabilityClass" for e in r["entities"])]
    if no_class:
        print(f"!! 无漏洞类型实体的 CVE 记录: {no_class}")


if __name__ == "__main__":
    main()
