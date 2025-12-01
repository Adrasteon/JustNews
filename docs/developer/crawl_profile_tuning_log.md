# Crawl Profile Tuning Log

## 2025-11-01 - BBC link_preview_only (max_articles=100)
 Environment: ${CANONICAL_ENV:-justnews-py312}, Crawl4AI 0.7.4, Playwright Chromium refreshed 2025-11-01.
 Command: `PYTHONPATH=. conda run -n ${CANONICAL_ENV:-justnews-py312} python - <<'PY' ... max_articles=100` after updating concurrency to 1, max links to 120.
- Metrics: total 100, unique 100, non-news 2, domain split {'www.bbc.co.uk': 76, 'www.bbc.com': 24}.
- Notes: include/exclude filters held steady; two seed URLs surfaced at the tail of the run for monitoring.
 Environment: ${CANONICAL_ENV:-justnews-py312}, Crawl4AI 0.7.4, Playwright Chromium refreshed 2025-11-01.
 Command: `PYTHONPATH=. conda run -n ${CANONICAL_ENV:-justnews-py312} python - <<'PY' ... max_articles=100` after updating concurrency to 1, max links to 120.
1. https://www.bbc.co.uk/news/articles/c3dnnpvjkjvo
2. https://www.bbc.co.uk/news/articles/c2emj9r4j22o
3. https://www.bbc.co.uk/news/articles/cvg441qyv2xo
4. https://www.bbc.co.uk/news/articles/c78zzezd5rlo
5. https://www.bbc.co.uk/news/articles/cvgkk1mkg0po
6. https://www.bbc.co.uk/news/articles/c4g78nj7701o
7. https://www.bbc.co.uk/news/articles/c993ygv9g25o
8. https://www.bbc.co.uk/news/articles/c93063q2lzeo
9. https://www.bbc.co.uk/news/articles/cn09r01k9yqo
10. https://www.bbc.co.uk/news/articles/cy8vrzpgxnro
11. https://www.bbc.co.uk/news/articles/cgkznrjme1po
12. https://www.bbc.co.uk/news/articles/c4gpwn5v072o
13. https://www.bbc.co.uk/news/articles/cnvee260n8eo
14. https://www.bbc.co.uk/news/articles/c5y44ly3vg2o
15. https://www.bbc.co.uk/news/articles/cwy77pnq05vo
16. https://www.bbc.co.uk/news/articles/crklljyx6mzo
17. https://www.bbc.co.uk/news/articles/ckg4q403rpzo
18. https://www.bbc.co.uk/news/articles/c9d666e12l5o
19. https://www.bbc.co.uk/news/articles/ckg14442r73o
20. https://www.bbc.co.uk/news/articles/c1j8gn16ep9o
21. https://www.bbc.co.uk/news/articles/ckg1y66y80ro
22. https://www.bbc.co.uk/news/articles/c93x4qn62y0o
23. https://www.bbc.co.uk/news/articles/cp08467m0zzo
24. https://www.bbc.com/news/articles/c3dnnpvjkjvo
25. https://www.bbc.com/news/articles/c2emj9r4j22o
26. https://www.bbc.com/news/articles/cvg441qyv2xo
27. https://www.bbc.com/news/articles/c78zzezd5rlo
28. https://www.bbc.com/news/articles/cvgkk1mkg0po
29. https://www.bbc.com/news/articles/c4g78nj7701o
30. https://www.bbc.com/news/articles/c993ygv9g25o
31. https://www.bbc.com/news/articles/c93063q2lzeo
32. https://www.bbc.com/news/articles/cn09r01k9yqo
33. https://www.bbc.com/news/articles/cy8vrzpgxnro
34. https://www.bbc.com/news/articles/cgkznrjme1po
35. https://www.bbc.com/news/articles/c4gpwn5v072o
36. https://www.bbc.com/news/articles/cnvee260n8eo
37. https://www.bbc.com/news/articles/c5y44ly3vg2o
38. https://www.bbc.com/news/articles/cwy77pnq05vo
39. https://www.bbc.com/news/articles/crklljyx6mzo
40. https://www.bbc.com/news/articles/ckg4q403rpzo
41. https://www.bbc.com/news/articles/c9d666e12l5o
42. https://www.bbc.com/news/articles/ckg14442r73o
43. https://www.bbc.com/news/articles/c1j8gn16ep9o
44. https://www.bbc.com/news/articles/ckg1y66y80ro
45. https://www.bbc.com/news/articles/c93x4qn62y0o
46. https://www.bbc.com/news/articles/cp08467m0zzo
47. https://www.bbc.co.uk/news/articles/c0jdd186l0go
48. https://www.bbc.co.uk/news/articles/cm2ww0e0jewo
49. https://www.bbc.co.uk/news/articles/cly44qwgnx0o
50. https://www.bbc.co.uk/news/articles/cpq11v5d1rno
51. https://www.bbc.co.uk/news/articles/c0qppe4vdevo
52. https://www.bbc.co.uk/news/articles/cq6z5e5y55eo
53. https://www.bbc.co.uk/news/articles/c1e3de5ny14o
54. https://www.bbc.co.uk/news/articles/c7977nlzvgpo
55. https://www.bbc.co.uk/news/articles/cn09x7jpvw7o
56. https://www.bbc.co.uk/news/articles/clyk1nq6v4lo
57. https://www.bbc.co.uk/news/articles/c891d43l8pyo
58. https://www.bbc.co.uk/news/articles/c3ep1epqjkpo
59. https://www.bbc.co.uk/news/articles/cr433x9zqq4o
60. https://www.bbc.co.uk/news/articles/cm277455158o
61. https://www.bbc.co.uk/news/articles/cy4007deg2qo
62. https://www.bbc.co.uk/news/articles/cr5eeqg150mo
63. https://www.bbc.co.uk/news/articles/c5ypp8jkp10o
64. https://www.bbc.co.uk/news/articles/cz0x8vdvkjgo
65. https://www.bbc.co.uk/news/articles/cx2dd7yyly9o
66. https://www.bbc.co.uk/news/articles/c20556ly45eo
67. https://www.bbc.co.uk/news/articles/cwykk10053eo
68. https://www.bbc.co.uk/news/articles/cy8vv5q2nw4o
69. https://www.bbc.co.uk/news/articles/cvgkkr7jj19o
70. https://www.bbc.co.uk/news/articles/cpq115389jro
71. https://www.bbc.co.uk/news/articles/cy400qdwgy2o
72. https://www.bbc.co.uk/news/articles/cj977j7j4j2o
73. https://www.bbc.co.uk/news/articles/c4gwwrz4dz5o
74. https://www.bbc.co.uk/news/articles/c77z4yxmnyro
75. https://www.bbc.co.uk/news/articles/clykwk9vwryo
76. https://www.bbc.co.uk/news/articles/c3w9x86p9ndo
77. https://www.bbc.co.uk/news/articles/cgqllevg9xeo
78. https://www.bbc.co.uk/news/articles/c8drr03v1qeo
79. https://www.bbc.co.uk/news/articles/c74jjjvpj91o
80. https://www.bbc.co.uk/news/articles/cm277kpvy5do
81. https://www.bbc.co.uk/news/articles/c3vnnnl771qo
82. https://www.bbc.co.uk/news/articles/cx27pe3z4m3o
83. https://www.bbc.co.uk/news/articles/c4gppj75kr1o
84. https://www.bbc.co.uk/news/articles/cg43xw5dyz0o
85. https://www.bbc.co.uk/news/articles/cwypwwjj32go
86. https://www.bbc.co.uk/news/articles/c2emmdnw82yo
87. https://www.bbc.co.uk/news/articles/cy5qql6kz5po
88. https://www.bbc.co.uk/news/articles/cze6w4e8kxeo
89. https://www.bbc.co.uk/news/articles/c2emmdx0x38o
90. https://www.bbc.co.uk/news/articles/czdjg92y00no
91. https://www.bbc.co.uk/news/articles/c5ype0gp7lgo
92. https://www.bbc.co.uk/news/articles/ce9drlgenjno
93. https://www.bbc.co.uk/news/articles/c5y930x81wpo
94. https://www.bbc.co.uk/news/articles/c6258nn89dgo
95. https://www.bbc.co.uk/news/articles/ce9d3kpdp4do
96. https://www.bbc.co.uk/news/articles/cyv862r7l2ro
97. https://www.bbc.co.uk/news/articles/c4g3mdvle78o
98. https://www.bbc.co.uk/news/articles/cwykqrlwwxqo
99. https://www.bbc.co.uk/news
100. https://www.bbc.com/news

## 2025-11-01 - BBC link_preview_only (strict seed skip, retry resets)
- Environment: ${CANONICAL_ENV:-justnews-py312}, Crawl4AI 0.7.4, Playwright Chromium refreshed 2025-11-01.
- Command: `PYTHONPATH=. conda run -n ${CANONICAL_ENV:-justnews-py312} python - <<'PY' ... max_articles=100` after updating concurrency to 1, max links to 120.
- Metrics: total 100, unique 98, non-news 0, domain split {'www.bbc.co.uk': 75, 'www.bbc.com': 23}.
- Notes: enabled `extra.strict_skip_seed_articles`, introduced per-request AsyncWebCrawler reinitialisation to absorb Playwright `Connection closed` errors, and set `timeout: 15` on link previews. Resulting harvest maintained article-only output with slight shortfall (2 duplicates filtered). Console run log retained in tuning session notes.

### Sample URLs
1. https://www.bbc.com/news/articles/c78zzezd5rlo
2. https://www.bbc.com/news/articles/c4g78nj7701o
3. https://www.bbc.com/news/articles/cn09r01k9yqo
4. https://www.bbc.co.uk/news/articles/c0jdd186l0go
5. https://www.bbc.co.uk/news/articles/cm2ww0e0jewo
6. https://www.bbc.co.uk/news/articles/c1e3de5ny14o
7. https://www.bbc.co.uk/news/articles/cwykqrlwwxqo
8. https://www.bbc.co.uk/news/articles/cq6z5e5y55eo
9. https://www.bbc.co.uk/news/articles/c4g3mdvle78o
10. https://www.bbc.co.uk/news/articles/cgqllevg9xeo
