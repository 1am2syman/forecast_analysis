# Demand Planning Director Review: Forecast Performance Dashboard

**Reviewer perspective:** Demand Planning Director, Fortune 500 FMCG business  
**Review type:** Product, functionality, analytical usefulness, chart quality, and purchase-readiness assessment  
**Dashboard reviewed:** Live real-data dashboard, desktop layout, expanded and collapsed navigation  
**Review date:** 27 August 2026  
**Overall judgment:** Strong forecast-performance observability foundation; not yet a complete director-level decision and action product

---

## Executive verdict

My first reaction is positive. This does not look like a generic BI template, and it does not hide behind a single accuracy percentage. It makes unusually good efforts to preserve source separation, comparable populations, forecast-vintage logic, coverage, denominators, and data-quality exceptions. Those are the hard analytical foundations that many polished planning dashboards get wrong.

The dashboard gives me confidence that the team understands forecast measurement. It is especially strong at answering:

- What is the aggregate forecast accuracy and bias in the selected population?
- Did the latest vintage improve or worsen the oldest vintage?
- How effective were revisions?
- How do TM and ML compare on an aligned, common population?
- Where are missing actuals, incomplete pairs, hierarchy issues, and source-coverage differences?
- Which product-month observations have the largest absolute errors?

However, it is currently better at **measurement and auditability** than at **executive decision support and operational action**. I can diagnose that performance is poor, and I can find bad observations, but the product does not yet close the loop from signal to accountable action. It does not tell me what my team should work on first, what business risk is attached to the error, whether we are above or below an agreed target, what caused the deterioration, who owns the exception, or whether an intervention was completed.

My concise commercial verdict is:

> I would support a paid pilot of this as a forecast-performance observability and forecast-value-add workbench. I would not yet buy it as an enterprise demand-planning product or make it the primary operating cockpit for my planning organization.

### Executive scorecard

| Dimension | Score | Director assessment |
| --- | ---: | --- |
| Analytical integrity | 8.5 / 10 | Source separation, aligned comparison, denominator transparency, and quality retention are strong. |
| Data trust and auditability | 8 / 10 | Very good population ledger and quality visibility; formula glossary and lineage need to be more user-facing. |
| Visual clarity | 6.5 / 10 | Clean and disciplined, but too small, sparse, and axis-light for executive interpretation. |
| Diagnostic usefulness | 7 / 10 | Good for analysts investigating accuracy, bias, revisions, and exceptions. |
| Decision usefulness | 5 / 10 | Lacks targets, business impact, prioritization, causal context, and recommended actions. |
| Workflow and accountability | 2.5 / 10 | No owners, notes, tasks, status, alerts, approvals, or exception resolution loop. |
| Enterprise usability | 4 / 10 | Missing saved views, role personalization, SSO/RBAC, scheduling, collaboration, and scalable hierarchy navigation. |
| Purchase readiness | 5 / 10 | Pilot-ready as an analytics module; not yet enterprise-product-ready. |

---

## Review context and expectations

I am evaluating this as a director responsible for a large FMCG portfolio across brands, channels, markets, and planning horizons. My recurring responsibilities include:

1. Running monthly demand reviews and contributing to S&OP/IBP.
2. Monitoring forecast accuracy, bias, and forecast value add.
3. Identifying material exceptions rather than inspecting every SKU.
4. Assigning actions to planners and commercial teams.
5. Understanding service, inventory, write-off, and working-capital implications.
6. Governing the choice between statistical, ML, and planner-adjusted forecasts.
7. Ensuring the numbers are trusted and reproducible.
8. Tracking whether process interventions improve outcomes over time.

This distinction matters because the dashboard is not being judged only as a visualization. It is being judged as a potential management product.

---

## What I like

### 1. The analytical contract is much more trustworthy than most dashboards

The strongest part of the product is not its color palette or layout. It is the discipline behind the numbers.

The dashboard visibly distinguishes:

- Forecast rows, pair rows, complete pairs, and missing vintages.
- Eligible observations and comparable observations.
- Actual-volume coverage numerator and denominator.
- Vintage A and Vintage B selection rules.
- Single-source vintage analysis from aligned TM-versus-ML source comparison.
- Source-only coverage from common-population performance.

That gives me confidence that the product will not casually compare unlike populations. In a real planning organization, this is critical. A visually impressive source comparison is useless if TM and ML were evaluated at different horizons, on different products, or against different actual populations.

### 2. TM-versus-ML comparison is correctly guarded

The separate modes for **Vintage revisions** and **TM vs ML** are conceptually correct. I like that the dashboard blocks TM-versus-ML analysis in single-source mode and offers an explicit **Enable comparison** action.

Once enabled, it clearly states:

- The exact aligned horizon.
- The common product-target population.
- TM-only and ML-only observations.
- Common actual volume.
- Source-specific accuracy, bias, absolute error, and coverage.
- ML-minus-TM deltas.
- Winner counts.

This is one of the most credible parts of the dashboard. It protects the user from an easy analytical mistake and makes the population mismatch visible instead of burying it.

### 3. Revision effectiveness is treated as a real process metric

I like the distinction between:

- Improved revisions.
- Worsened revisions.
- Neutral revisions.
- Unchanged observations.

I also like that unchanged rows are excluded from the revision-effectiveness denominator. The dashboard shows total error improvement in KL and exposes whether the latest vintage actually added value. This is directly relevant to forecast value-add governance.

The current result—revision effectiveness around half, with the latest vintage worsening aggregate accuracy—is exactly the kind of uncomfortable signal a director needs to see.

### 4. Data quality is first-class rather than an appendix

The **Data quality** page is unusually good in principle. It keeps hierarchy mapping, actual availability, vintage-pair completeness, and source availability visible and downloadable.

The strongest behaviors are:

- Non-blocking quality problems remain auditable.
- Missing actuals remain visible instead of disappearing from coverage.
- Source-only observations are separated from common-source comparisons.
- Quality categories have dedicated CSV exports.
- The dashboard distinguishes a valid input pipeline from downstream exceptions.

I would rather have a dashboard openly tell me that 1,057 observations lack actuals than silently give me a cleaner-looking but less representative accuracy number.

### 5. The population ledger is excellent

The persistent scope line at the top is one of the best interface elements. It continuously states the mode, source, target range, product count, horizons, actual volume, eligible rows, comparable rows, and coverage.

This prevents a common failure in BI tools: forgetting what population produced the chart currently on screen.

### 6. The shared filter principle is correct

The filter drawer explicitly says that every tab, count, and download recomputes from the same scope. That is the right product contract. The controls cover a broad set of real analytical needs:

- Source and comparison mode.
- Target period.
- Brand and parent product.
- Horizon.
- Vintage rules.
- Revision direction and outcome.
- Accuracy, bias, and error filters.
- Ranking and Top N.
- Actual, hierarchy, pair, and source-availability states.
- Zero forecasts and vintage completeness.

The scope is analytically serious.

### 7. The exception download is transparent

The exception page clearly distinguishes total active rows from the preview row limit, and it states that the CSV contains every active row and all audit columns. That is a good detail. It avoids the common ambiguity of whether an export contains only the ten rows visible on screen.

### 8. Navigation is simple and the collapse behavior is useful

The left vertical navigation is easy to understand. The collapsed rail behaves gracefully and releases substantial screen space without losing access to pages. The state persists, and the workspace uses the reclaimed width. This is useful for dense analysis pages.

The navigation labels are also meaningful: Overview, Trends, Comparison, Product history, and Data quality. I do not need training to understand the broad information architecture.

### 9. The interface is calm and professional

The porcelain, graphite, teal, and amber visual system feels like an analytical instrument rather than a marketing dashboard. The use of red is restrained. The design does not rely on glossy gradients, oversized cards, or decorative animation.

For a planning team that spends hours in the product, that restraint is valuable.

### 10. Empty and blocked states are handled honestly

The product does not force a meaningless chart when the selected analytical mode is invalid. It displays a clear message and a corrective action. Product history also explains when stability metrics cannot be calculated because only one vintage exists.

That honesty strengthens trust.

---

## What I do not like

### 1. The dashboard lacks an executive performance frame

The Overview tells me that forecast accuracy is 73.9%, bias is +20.5%, and revision effectiveness is 49.1%, but it does not tell me whether those numbers are acceptable.

I need to see:

- Accuracy target.
- Bias tolerance band.
- Revision-effectiveness target.
- Current month versus target.
- Rolling 3-month and 12-month performance.
- Prior period and prior-year comparison.
- Status such as On target, Watch, or Off target.

Without targets, the dashboard measures but does not manage.

### 2. The default Overview is too audit-heavy and not action-oriented enough

The first screen gives prominent space to forecast rows, pair rows, complete pairs, missing vintages, and vintage-rule names. Those details are valuable for analysts and model governance, but they are not the first questions I ask in a demand review.

My first screen should answer:

1. Are we on target?
2. Where is the largest material risk?
3. What changed since last review?
4. Which five exceptions require intervention?
5. What actions are open and who owns them?

The current Overview makes me work to translate the metric contract into a management agenda.

### 3. Typography is too small and too technical for a director cockpit

The density is impressive, but many labels and metadata lines are extremely small. The monospace utility text reinforces auditability, but it also makes the product feel like an engineering console.

This will be difficult in a meeting-room setting, on a shared screen, or for executives who are not sitting close to a high-resolution monitor.

I would increase the functional type scale for:

- Scope values.
- Axis labels.
- KPI captions.
- Quality explanations.
- Table values.

Technical metadata can remain small in a details drawer.

### 4. The accuracy metric is not named in familiar business language

The dashboard calls the metric **Forecast accuracy**, but the formula is effectively `1 − WAPE`. That is defensible, and preserving negative values is correct, but the product should state the convention prominently.

Different companies use different definitions of forecast accuracy. A director needs to know immediately:

- Is this 1 − WAPE?
- Is it volume-weighted?
- What rows are eligible?
- Are negative values possible?
- Is the result comparable to the company target?

The numerator/denominator caption is good, but a metric glossary and an explicit label such as **Forecast accuracy (1 − WAPE)** would reduce disputes.

### 5. Several charts are visually clean but analytically under-specified

The charts often omit axis names, tick labels, target lines, value scales, or legends. Native browser hover titles exist in places, but that is not sufficient for a business product.

A chart should be interpretable in a screenshot, PDF, or meeting without requiring precise mouse hovering.

### 6. The “Forecast vs actual” trend is not actually a clear forecast-versus-actual comparison

When I select **Forecast vs actual**, the main chart presents a forecast series, while actual volume is not displayed as a clearly comparable second series with its own legend and scale. Actual can be discovered through hover evidence, but the visual promise of “versus” is not fulfilled.

I would expect either:

- Two directly comparable lines: forecast and actual.
- Grouped bars: forecast and actual.
- A variance band or error bars below the volume chart.

This is a functionality and labeling issue, not merely a cosmetic preference.

### 7. The Overview chart combines accuracy and actual volume without a proper volume axis

The Overview shows an accuracy line with pale actual-volume bars. The bars appear to be independently normalized and do not have a visible right-side scale. That makes the chart aesthetically useful but quantitatively weak.

A director cannot estimate the actual volume represented by a bar from the visual alone. I would split this into aligned small multiples or add a clearly labeled secondary axis.

### 8. Blank future months are not explained

The target range extends beyond the last month with actuals, so the trend axis continues while the accuracy line stops. The dashboard does not visibly mark:

- Actuals data cutoff.
- Forecast-only future period.
- Closed versus open months.

That creates unnecessary uncertainty. Is the chart broken, are actuals late, or are those future months intentionally not measurable yet?

A vertical **Actuals through Apr 2026** marker and shaded future area would solve this.

### 9. Product selection is not scalable

The product picker is a native single-select dropdown with a long list of codes and descriptions. The shared product filter is also effectively a single selection, despite a large portfolio.

For a Fortune 500 portfolio I need:

- Search as I type.
- Multi-select.
- Hierarchical drill from category to brand to sub-brand to product.
- Recent selections.
- Pinned products.
- Selection by pasted list of codes.

A 141-product native dropdown is already cumbersome. It will not scale to thousands of SKUs or customer-product combinations.

### 10. The first product-history example can be a weak or misleading first impression

A default product and target month may have no actual or insufficient history. The product correctly explains the issue, but as an initial experience it makes the main product-detail view look empty.

The default should select a representative product-month with:

- Positive actual.
- At least two vintages.
- Material volume.
- A meaningful revision story.

Alternatively, the page should start with a prompt to choose an exception.

### 11. There is no connected drill-through

I cannot click a heatmap cell, scatter point, horizon bar, quality exception, or table row and arrive at the corresponding product history with filters preserved. The dashboard has drill-down content, but it lacks a connected drill-down journey.

This is one of the largest experience gaps. The product contains the right views, but the views behave like separate reports rather than one investigative workflow.

### 12. The dashboard does not support collaboration or accountability

There are no:

- Owners.
- Comments.
- Root-cause tags.
- Action statuses.
- Due dates.
- Approval states.
- Planner explanations.
- Exception dispositions.
- Audit trail of who reviewed what.

A director can identify a problem but cannot run a process around it.

### 13. “Live data” may overstate the refresh model

The dashboard shows a refresh timestamp, which is good. However, a **Live data** badge suggests continuous or near-real-time data. If the inputs refresh daily, weekly, or monthly, the language should say **Data current through [date]** or **Last successful refresh**.

Enterprise users are sensitive to the difference between live, refreshed, and period-closed data.

---

## What is missing

### A. Missing decision support

The product needs a layer that converts performance into priorities.

Required additions:

- Top five business risks by volume, revenue, or margin.
- Top five opportunities where correction would recover the most error.
- A Pareto view showing how much of total absolute error is concentrated in the worst products.
- Recommended investigation path, such as “Bias concentrated in Brand X at M−2.”
- Materiality thresholds configured in business terms.
- A clear weekly or monthly action list.

### B. Missing targets and benchmarks

I would add configurable targets for:

- Forecast accuracy by hierarchy and horizon.
- Bias tolerance.
- Revision effectiveness.
- Coverage.
- Forecast completeness.
- Source adoption or source performance.

Benchmarks should include:

- Prior month.
- Rolling 3 months.
- Rolling 12 months.
- Same period last year.
- Naive baseline.
- Statistical baseline.
- Planner-submitted forecast.
- Consensus/final plan.

### C. Missing forecast value-add chain

The current vintage and TM/ML comparisons are a strong start, but a demand planning director needs a complete FVA chain:

```text
Naive forecast → statistical/ML baseline → planner adjustment → commercial override → consensus plan → final approved demand plan
```

For every stage, show:

- Accuracy.
- Bias.
- Absolute error.
- Incremental value add.
- Percentage of observations improved.
- Material deterioration.
- Who or what introduced the change.

Without this chain, I can compare sources and vintages but cannot govern the full planning process.

### D. Missing business impact translation

KL is operationally meaningful, but director-level prioritization often requires monetary and service implications.

Add optional translations into:

- Net sales value.
- Gross margin at risk.
- Inventory/working capital exposure.
- Obsolescence or write-off risk.
- Service-level or out-of-stock risk.
- Capacity or supply-feasibility risk.

The dashboard should not pretend to calculate these without validated inputs, but it should have a product path for them.

### E. Missing demand context

Forecast error alone does not explain why a forecast failed. I want overlays and segmentation for:

- Promotions.
- Price changes.
- Distribution gains/losses.
- Customer events.
- New product introductions.
- Product discontinuations.
- Seasonality.
- Supply constraints and lost sales.
- One-off demand spikes.
- Baseline versus incremental demand.

These should be annotations and filters, not causal claims.

### F. Missing operational workflow

The exception list should become an action center with:

- Owner.
- Root-cause category.
- Status.
- Due date.
- Comment.
- Agreed action.
- Expected impact.
- Resolution evidence.
- Reopen/escalate behavior.

Even if forecast editing remains out of scope, exception management is essential for a sellable planning product.

### G. Missing enterprise controls

Before enterprise purchase I would require:

- SSO and role-based access control.
- Audit logs.
- Data-retention policy.
- Configurable metric definitions and thresholds.
- Environment and release management.
- Refresh monitoring and failure alerts.
- Saved views and default role-based landing pages.
- Shareable URLs that preserve filter state.
- Scheduled email/PDF/PowerPoint distribution.
- API access and governed exports.
- Support for business-unit, market, customer, channel, category, and product hierarchies.

### H. Missing alerting

The product should proactively alert when:

- Bias exceeds tolerance for consecutive periods.
- Accuracy deteriorates materially.
- A high-volume product has a large latest-vintage error.
- A revision worsens the forecast materially.
- Actuals are missing past the expected close date.
- A source loses coverage.
- An exception remains unassigned or overdue.

### I. Missing saved analysis state

Filters are comprehensive, but I cannot see support for:

- Saving a view.
- Naming a scenario.
- Bookmarking a product or brand.
- Sharing the exact scope with another user.
- Returning to my last working context.
- Comparing two saved scopes.

This is important for recurring S&OP routines.

---

## What is redundant or unnecessary

### 1. Too much repeated technical provenance in the main interface

The dashboard repeatedly shows versions of:

- Canonical analysis data.
- Metric contract v2.
- Active real-data scope.
- Metrics computed by `forecast_analysis`.
- Source filenames in the footer.

This is valuable for governance but too prominent for daily director use. Consolidate it into one **Data & metric lineage** drawer.

### 2. Population counts are repeated in several places

Eligible, comparable, forecast rows, pair rows, and coverage appear in the scopebar, population strip, KPI captions, and quality pages.

Some repetition is protective, but the Overview can be simplified. Keep the top scope ledger and move deeper population-grain details to a tooltip or audit panel.

### 3. Eight equal-weight Overview KPIs are too many

Actual volume, forecast volume, bias, absolute error, and MAE are related. Displaying all eight cards with equal visual importance dilutes the management signal.

I would promote four primary indicators:

1. Forecast accuracy versus target.
2. Bias versus tolerance.
3. Absolute error/value at risk.
4. Revision effectiveness/FVA.

Coverage and data quality should remain visible as trust indicators. Actual and forecast volume can sit in the trend context.

### 4. The Comparison page title combines two different jobs

“TM vs ML, and how revisions land” is accurate but awkward. The selected subview should control the page title:

- **Forecast revision value add**
- **TM versus ML performance**

This would reduce cognitive load.

### 5. Forecast exceptions do not naturally belong under Product history

Product history is a single-entity investigation. Forecast exceptions are a portfolio work queue. They should be separate destinations or part of a dedicated **Exceptions & actions** page.

### 6. Data quality occupies a primary director navigation slot

I want data quality visible, and the warning badge is useful. However, most directors will not spend equal time there. It could be a utility destination or a role-personalized page for data stewards, while the primary navigation makes room for **Exceptions & actions**.

### 7. Large quality tiles use too much space for simple counts

The status tiles are readable but leave large empty areas. A compact stacked bar, percentage distribution, materiality summary, and exception list would communicate more with less space.

---

## Questions the dashboard does not answer

### Executive performance questions

- Are we meeting the forecast-accuracy target?
- Is 73.9% good for this portfolio, horizon, and demand pattern?
- Is bias improving or worsening over the last three months?
- How does current performance compare with last year?
- Which business units are off target?
- What percentage of volume is forecast within agreed tolerance?
- Is the current deterioration statistically meaningful or normal variation?

### Priority and materiality questions

- Which five products or brands explain most of the total error?
- What percentage of error is concentrated in the top 10 exceptions?
- Which problems matter most in revenue, margin, service, or working capital?
- Which exceptions are high error but low business impact?
- Where can the team recover the most value with the least effort?

### Process and forecast-value-add questions

- Did planner overrides add value over the baseline?
- Did commercial overrides improve or damage the plan?
- Which planners, categories, or markets consistently add value?
- Where should ML be trusted, and where should TM remain primary?
- Does ML outperform TM consistently across horizons and segments?
- Is the performance difference large enough to justify adoption and operating cost?
- Are late revisions more effective than early revisions?
- How much change occurs inside the frozen planning horizon?

### Root-cause questions

- Was an error driven by promotion, distribution, price, seasonality, supply constraint, launch, or discontinuation?
- Is high bias systematic or caused by one outlier month?
- Are misses concentrated in intermittent or volatile demand?
- Did actual demand change, or did the planning process change?
- Why did a specific revision worsen the result?

### Risk questions

- What service risk does the under-forecast create?
- What excess inventory or obsolescence risk does the over-forecast create?
- Which future months are most exposed?
- What is the uncertainty range around the forecast?
- Which products lack enough history to trust the model?

### Accountability questions

- Who owns each major exception?
- Has it been reviewed?
- What action was agreed?
- When is the action due?
- Did the action improve the next forecast cycle?
- Which issues are overdue or repeatedly reopened?

### Data trust questions

- When did actuals close for each market?
- Which refresh failed or arrived late?
- What business definition of accuracy is configured?
- Are thresholds global or hierarchy-specific?
- Which source system and forecast version generated each row?
- Can I reproduce the exact meeting view later?

---

## Chart-by-chart review

### 1. Overview: Monthly accuracy and volume

**What works**

- Gives immediate trend context beneath the KPI cards.
- Preserves negative accuracy rather than clipping it.
- Includes point-level native hover evidence with actual, forecast, and count.
- Actual volume is visually present.

**What does not work**

- Actual-volume bars have no visible quantitative axis.
- Accuracy and volume are combined without enough scale explanation.
- Month labels omit years, so repeated months are ambiguous.
- The line stops when actuals stop, but the future period is not explained.
- No target line or tolerance band exists.
- No period-over-period delta or rolling average exists.

**Improvement**

Use two aligned panels:

1. Forecast accuracy and bias versus target/tolerance.
2. Forecast and actual volume with variance.

Add year-aware labels, actuals cutoff, future shading, 3-month rolling line, prior-year comparison, and click-through to exceptions.

### 2. Trends: Monthly performance

**What works**

- Metric selection is useful.
- The same active population is retained.
- TM and ML use consistent colors.
- Native hover exposes row evidence.

**What does not work**

- “Forecast vs actual” is not a genuine two-series comparison.
- Axis units are not explicit.
- There is no target or benchmark.
- There is no zoom, brush, range selector, or granularity control.
- The chart cannot cross-filter the rest of the dashboard.

**Improvement**

Add explicit y-axis titles, complete tooltips, selected-period highlighting, rolling windows, benchmark overlays, and a click/brush interaction that updates the heatmap and exception table.

### 3. Performance by horizon

**What works**

- Horizons are ordered from longer range to near term.
- Aligned source comparison is possible.
- The compact form fits the page.

**What does not work**

- Bars have no axis or scale.
- For signed bias, absolute bar length hides direction.
- Actual volume and observation count are not visible in the chart itself.
- Differences of one or two points are hard to judge.
- No target curve or horizon-specific target exists.

**Improvement**

Use a dot or line chart with a zero line for signed metrics. Show TM and ML side by side at each horizon, include actual volume and observation count, and allow horizon-specific targets. For accuracy, add confidence or sample-size context.

### 4. Brand × target-month heatmap

**What works**

- Worst-first sorting is appropriate.
- Signed and magnitude metrics can be selected.
- Quality groups can remain visible.
- Cell hover includes brand, month, value, and count.

**What does not work**

- There is no color legend.
- Month labels omit years.
- Only the last six months and eight brands are shown, but the truncation is not prominent enough.
- The color scale can be dominated by a large negative outlier.
- A sequential-looking palette is not ideal for signed metrics.
- Cells are not clickable.

**Improvement**

Use metric-specific color scales:

- Diverging around zero for bias and accuracy delta.
- Thresholded red/amber/green against target for accuracy.
- Sequential magnitude scale for absolute error.

Add a visible legend, robust percentile clipping, explicit “Worst 8 of N brands,” year labels, and click-through to filtered exceptions.

### 5. Revision outcomes

**What works**

- Improved, worsened, neutral, and unchanged are clearly separated.
- The table shows counts, revision KL, and error improvement.
- Revised-up and revised-down percentages add useful context.

**What does not work**

- Counts are not normalized into percentages of total and materially revised populations.
- No hierarchy or horizon split is immediately visible.
- There is no trend showing whether revision effectiveness is improving over time.

**Improvement**

Add percentage labels, a monthly revision-effectiveness trend, and a decomposition by horizon/brand. Show the 80/20 contributors to worsened revisions.

### 6. Revision amount vs error improvement scatter

**What works**

- Correct zero references create meaningful quadrants.
- Bubble size reflects actual volume.
- Improved and worsened points are visually distinct.
- Hover identifies product and month.

**What does not work**

- Axes have no labels or tick values.
- Quadrants are not named.
- Dense central points overplot.
- I cannot click, select, or lasso points.
- There is no linked exception table.

**Improvement**

Label axes and quadrants:

- Revised up and improved.
- Revised up and worsened.
- Revised down and improved.
- Revised down and worsened.

Add zoom, lasso, density/hexbin mode, point click-through, and a linked table of selected observations.

### 7. TM-versus-ML paired absolute-error scatter

**What works**

- The diagonal is the right reference.
- Common-population comparison is analytically correct.
- Winner counts summarize the result.
- Coverage differences remain separate.

**What does not work**

- Axes are unlabeled and have no ticks.
- With more than a thousand observations, points overlap heavily near the origin.
- The chart does not reveal where ML wins by a commercially material amount.
- There is no segment/horizon small multiple.
- No click-through exists.

**Improvement**

Use log or square-root scales where appropriate, add marginal distributions, label axes, show a materiality band around the diagonal, and allow coloring by brand, horizon, volume tier, or winner. Link selected points to product history.

### 8. Product chronological forecast development

**What works**

- Forecasts are plotted chronologically by calculation month.
- TM and ML remain distinct.
- Actual is conceptually available as a reference.
- Stability metrics and consecutive revisions are shown alongside the chart.
- Insufficient-history states are explicit.

**What does not work**

- No y-axis values are shown.
- Forecast values require precise hover.
- The default selected target may have no actual.
- Actual-demand history is not shown; only the selected target’s reference is relevant.
- Product selection is not searchable enough.
- There is no direct navigation from an exception to this page.
- The chart does not show forecast freeze dates, overrides, or events.

**Improvement**

Add a labeled y-axis, value labels for selected points, target actual reference with variance, event annotations, and a one-click path from exceptions and scatter points. Support search, recent items, and previous/next exception navigation.

### 9. Forecast exceptions table

**What works**

- Defaults to largest Vintage B absolute error.
- Supports text search and row-limit selection.
- Shows source, product, brand, target, actual, latest forecast, absolute error, bias, outcome, and pair/mapping status.
- Export includes more audit detail than the preview.

**What does not work**

- Headers are not interactively sortable.
- Rows are not clickable.
- There is no owner, cause, status, or action.
- “All loaded” means the loaded preview, not all active rows; the summary explains it, but the label can still confuse.
- No Pareto or cumulative-error context exists.
- No bulk selection or assignment exists.

**Improvement**

Turn it into an action table with sortable columns, column chooser, sticky header, row click-through, bulk actions, ownership, status, comments, and a Pareto summary.

### 10. Data-quality views

**What works**

- Categories are logically separated.
- Counts, product/month coverage, and example exceptions are visible.
- Each category can be exported.
- Good states and exception states are distinguished.

**What does not work**

- Counts mix grains—observations, products, and months—without always making the primary grain immediately obvious.
- All four categories receive similar warning treatment even when business impact differs materially.
- Large tiles do not show percentage share clearly.
- Exception previews repeat the same product many times and can hide breadth.
- No owner or remediation status exists.

**Improvement**

Show percentage, actual-volume impact, first-seen date, affected products, and remediation owner. Deduplicate previews by product where useful, with expansion into product-month detail.

---

## Metrics I would add

### Must-add management metrics

1. **Forecast accuracy target variance** — actual accuracy minus target in percentage points.
2. **Bias tolerance status** — within or outside configured band.
3. **Rolling 3-month and rolling 12-month accuracy/bias**.
4. **Prior-period and prior-year change**.
5. **Hit rate within tolerance** — percentage of observations within agreed absolute or percentage error.
6. **Pareto concentration** — percentage of total absolute error explained by top 10/20 products.
7. **Forecast value add by stage** — versus naive, baseline, planner, commercial, and consensus forecast.
8. **Systematic bias streak** — consecutive over- or under-forecast periods.
9. **Forecast completeness** — future product-months with a submitted forecast versus required population.
10. **Data timeliness** — actual and forecast refresh SLA compliance.

### Strongly recommended segmentation metrics

- Accuracy and bias by volume class.
- Accuracy and bias by lifecycle: NPI, mature, declining, discontinued.
- Accuracy and bias by promotion versus base demand.
- Forecastability/volatility segment.
- Intermittent-demand segment.
- Horizon-specific target attainment.
- Planner or team FVA.
- Brand/category/customer/market contribution to total error.

### Business impact metrics

Where validated commercial and supply inputs exist:

- Revenue at risk.
- Margin at risk.
- Inventory exposure.
- Working-capital exposure.
- Waste/obsolescence exposure.
- Service-risk volume.
- Lost-sales exposure.

### Metrics I would not add as more headline cards

I would not simply add MAPE, RMSE, sMAPE, tracking signal, and ten statistical scores to the Overview. More metrics are not automatically more useful.

- MAPE is unstable around low and zero actuals.
- RMSE can be useful diagnostically but is hard to manage against in KL-heavy portfolios.
- Technical model scores should sit in an analyst/model-governance view.

The Overview should remain selective. Add metrics only when they change a decision.

---

## Page organization

The current five-page structure is coherent, but I would reorganize it around the planning workflow rather than the data model.

### Recommended navigation

#### 1. Executive cockpit

Purpose: answer “Are we on target, what changed, and what requires action?”

Include:

- Four primary KPIs versus target.
- Rolling trend.
- Top risks and opportunities.
- Open actions.
- Data trust indicator.
- Short narrative summary generated from deterministic rules, not unsupported causal claims.

#### 2. Performance diagnosis

Purpose: explain where error and bias are concentrated.

Include:

- Month trend.
- Horizon curve.
- Hierarchy heatmap.
- Pareto contribution.
- Segmentation by lifecycle, promotion, and forecastability.

#### 3. Forecast value add

Purpose: govern revisions, sources, and planning stages.

Include:

- Vintage revision mode.
- TM-versus-ML mode.
- Baseline-to-consensus FVA waterfall.
- Winner segments.
- Revision timing and effectiveness.

#### 4. Exceptions & actions

Purpose: run the team’s work queue.

Include:

- Prioritized exceptions.
- Business impact.
- Owner and status.
- Root-cause tags.
- Due date and comments.
- Bulk assignment and export.

#### 5. Product deep dive

Purpose: investigate one product-target combination.

Include:

- Vintage history.
- Actual history.
- Events and overrides.
- Stability.
- Related actions.
- Previous/next exception navigation.

#### 6. Data trust

Purpose: govern actuals, hierarchy, forecast completeness, source coverage, refreshes, and metric lineage.

This can remain prominent for analysts and data stewards but does not need equal weight in the director’s default navigation.

### Role-based landing pages

- **Director:** Executive cockpit and open actions.
- **Demand planning manager:** Performance diagnosis and team FVA.
- **Demand planner:** Exceptions and product deep dive.
- **Data steward:** Data trust and remediation.
- **Model owner:** TM-versus-ML and model-segment performance.

This would make the same analytical foundation more commercially scalable.

---

## What I would not want to see in the final product

- A “green” aggregate KPI that hides low coverage or material exclusions.
- A forecast-accuracy number without the company’s agreed formula and target.
- Negative accuracy clipped to zero.
- TM and ML compared on unmatched horizons or populations.
- Future months shown as unexplained blank space.
- Native browser tooltips as the only source of chart detail.
- Raw filenames and implementation module names occupying permanent executive screen space.
- Long product-code dropdowns without search.
- A list of exceptions without materiality, ownership, and resolution status.
- Automated causal statements such as “promotion caused the miss” without validated causal evidence.
- More KPI cards merely to make the dashboard look comprehensive.
- A “Live data” claim without a refresh SLA and current-through date.

---

## Functionality priorities

### P0 — Required before a serious director pilot

1. Add target lines, tolerance bands, and prior-period comparison.
2. Fix forecast-versus-actual chart semantics.
3. Add explicit axes, units, years, and data-cutoff markers to every chart.
4. Enable chart-to-detail and table-to-product drill-through.
5. Replace long single-selects with searchable hierarchy-aware multi-select controls.
6. Add sortable exception columns and a Pareto view.
7. Add a visible metric glossary and configurable business definitions.
8. Make the default product-detail selection representative.
9. Add saved/shareable filter state.
10. Clarify loaded-preview versus full-export language.

### P1 — Required for paid multi-team adoption

1. Full forecast-value-add chain.
2. Owners, comments, status, due dates, and exception workflow.
3. Saved views, bookmarks, and scheduled reporting.
4. Alerts and threshold subscriptions.
5. Promotion, lifecycle, and event context.
6. Business hierarchy support beyond brand and parent product.
7. Role-based landing pages.
8. Revenue/margin/inventory materiality where data is available.

### P2 — Required for enterprise platform positioning

1. SSO, RBAC, and audit logs.
2. Governed integrations and refresh monitoring.
3. Configurable metric and threshold administration.
4. API, scheduled exports, and collaboration integrations.
5. Scenario comparison and decision tracking.
6. Scalable performance across enterprise-level SKU-location-customer grains.
7. Formal support, uptime, security, and data-governance commitments.

---

## Would I buy it?

### Commercial buying frame

| Buying question | Answer |
| --- | --- |
| Primary buyer | Demand Planning Director, Planning Excellence leader, Forecasting/Analytics lead, or model-governance owner. |
| Best current use case | Govern forecast performance, forecast revisions, TM-versus-ML comparisons, coverage, and data trust from a shared metric contract. |
| Differentiators | Source-safe comparisons, transparent denominators, explicit comparable populations, vintage-level revision effectiveness, and unusually visible quality diagnostics. |
| Primary blockers | No target-management layer, limited chart interaction, no action workflow, no causal/event context, no saved collaboration state, and no enterprise identity/governance controls. |
| Pilot conditions | Agreed metric definitions, reliable refresh, fixed P0 visualization/drill-through issues, saved scopes, representative hierarchy coverage, and clear support ownership. |
| Expansion condition | Demonstrated adoption in monthly demand reviews plus measurable reduction in time to identify, assign, and resolve material forecast exceptions. |

### As the complete demand-planning product: No, not yet

It does not yet replace a planning platform or an operating cadence. It cannot manage exceptions, assign actions, preserve decisions, incorporate causal context, or connect forecast performance to business risk. It also lacks the enterprise controls required for a Fortune 500 deployment.

### As a forecast-performance analytics module: Yes, conditionally

I would approve a controlled pilot if:

- It integrates reliably with our forecast, actual, hierarchy, and planning-stage data.
- Metric definitions are configurable and signed off by Finance and Planning Excellence.
- The P0 chart and drill-through issues are fixed.
- Saved views and shareable scopes are added.
- Product support and refresh monitoring are credible.
- The price reflects that this is an analytical workbench, not a full planning suite.

### What would make me champion it

I would become a strong internal sponsor if the product evolves into:

> A trusted forecast-performance observability and action platform that measures forecast value add, prioritizes material exceptions, connects them to owners and business impact, and proves whether the planning process is improving.

The hard analytical core is already promising. The next investment should not be more decorative charts. It should be the decision and action layer.

### Final purchase score

- **Current product:** 5 / 10 purchase readiness.
- **After P0:** 7 / 10; credible director pilot.
- **After P1:** 8.5 / 10; compelling specialist product.
- **After P2:** eligible for enterprise platform consideration.

---

## Final recommendation

Proceed, but position the product honestly.

Do not sell it today as “demand planning software.” Sell it as a **forecast performance, forecast value-add, and data-trust workbench**. That positioning matches what it currently does well and avoids unfavorable comparison with platforms that include workflow, collaboration, scenarios, and operational planning.

The product has a better measurement foundation than many more mature-looking tools. If the next release connects the current analytics to targets, materiality, drill-through, ownership, and action tracking, I would take it seriously as a product rather than only as a dashboard.
