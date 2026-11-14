"""Resume extraction and *candidate* skill suggestions, never fabricated claims."""
import re
SKILL_TERMS = {
    "Burp Suite": ["burp suite","burpsuite"],
    "OWASP Top 10": ["owasp top 10","owasp top ten"],
    "API Security": ["api security","api penetration testing","api pentest"],
    "Web Application Testing": ["web application testing","web application penetration"],
    "Mobile Application Security": ["mobile application security","mobile penetration testing","android pentest"],
    "Network Penetration Testing": ["network penetration testing","network pentest"],
    "Cloud Security": ["cloud security","aws security","azure security"],
    "AWS": ["amazon web services","aws"],
    "Azure": ["azure"],
    "Python": ["python"],
    "Bash": ["bash scripting","bash"],
    "JavaScript": ["javascript"],
    "SQL Injection": ["sql injection","sqli"],
    "XSS": ["cross-site scripting","cross site scripting","xss"],
    "SSRF": ["server-side request forgery","ssrf"],
    "IDOR": ["insecure direct object reference","idor"],
    "Threat Modeling": ["threat modeling","threat modelling"],
    "SAST": ["static application security testing","sast"],
    "DAST": ["dynamic application security testing","dast"],
    "Secure Code Review": ["secure code review","security code review"],
    "Nmap": ["nmap"],
    "Metasploit": ["metasploit"],
    "Nuclei": ["nuclei"],
    "Linux": ["linux"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes"],
}
def suggest_skills(text: str):
    lowered=text.lower()
    return [skill for skill,patterns in SKILL_TERMS.items()
            if any(re.search(r"(?<![a-z0-9])"+re.escape(p)+r"(?![a-z0-9])",lowered)
                   for p in patterns)]

def suggest_roles(text):
    """A role-family suggestion is not a claim of eligibility."""
    low=text.lower()
    options={
        "Penetration Tester":["penetration testing","penetration tester","pentesting","pentest"],
        "Application Security Engineer":["application security","appsec","web application security"],
        "Offensive Security Engineer":["offensive security","red teaming","red team"],
        "Product Security Engineer":["product security","secure development lifecycle","secure code review"],
    }
    return [role for role,evidence in options.items() if any(x in low for x in evidence)]
