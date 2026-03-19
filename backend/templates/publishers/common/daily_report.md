# {{ title }}

{% if date %}日期: {{ date }}{% endif %}

---

{% for paper in papers %}
## {{ loop.index }}. {{ paper.title }}

**作者**: {{ paper.authors|join(', ') if paper.authors else '未知' }}

**链接**: [{{ paper.arxiv_id or '查看原文' }}]({{ paper.url }})

{% if paper.summary %}
**摘要**:
{{ paper.summary }}
{% endif %}

---

{% endfor %}

{% if footer %}
{{ footer }}
{% endif %}