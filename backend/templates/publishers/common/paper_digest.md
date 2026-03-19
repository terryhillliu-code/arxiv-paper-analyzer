# 论文摘要模板

{{ title or '今日论文摘要' }}

{% for paper in papers %}

---
### {{ paper.title }}

{% if paper.one_line_summary %}
> {{ paper.one_line_summary }}
{% endif %}

- **作者**: {{ paper.authors|join(', ') if paper.authors else '未知' }}
- **机构**: {{ paper.institutions|join(', ') if paper.institutions else '未知' }}
- **链接**: {{ paper.url }}

{% if paper.tags %}
- **标签**: {{ paper.tags|join(' · ') }}
{% endif %}

{% if paper.summary %}
{{ paper.summary }}
{% endif %}

{% endfor %}