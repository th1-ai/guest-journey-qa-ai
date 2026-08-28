# FAQ (fixture data)

Sample questions and answers, in the same shape a real `knowledge/faq.md`
would use. This agent has no guest-facing prompts (see `docs/how-it-works.md`
"The one LLM call"), so this file exists mainly so `make doctor`'s knowledge
check has something to find - see `knowledge/README.md` for what actually
matters here.

**Q: Why did a property's overall score change from last week?**
A: Re-run `python3 tools/report.py` and compare `by_property` across two
weeks, or read the `warnings` list on the scorecard - a category with no
signal this week is not the same as a category that was checked and found
clean. See `docs/how-it-works.md` "Scoring rubric".

**Q: Why does Aurora Ridge Lodge always sort first in some views but last in others?**
A: The QA scorecard always puts the flagship (`config/agent.yaml: flagship`)
first, then the rest weakest-overall-first. `make report`'s "by property"
list is sorted the same way, worst first, so the property needing the most
attention is always at the top.
