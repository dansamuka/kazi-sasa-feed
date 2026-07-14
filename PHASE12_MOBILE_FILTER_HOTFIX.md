# Phase 12 Mobile Filter UI Hotfix

The job-board filter row can now be collapsed on every screen size and starts collapsed on screens up to 760px wide.

## Behaviour

- Mobile filters start hidden so the role list is not covered by the large filter set.
- A full-width **Show filters / Hide filters** control displays the active-filter count.
- Mobile search/filter controls are no longer sticky over the results list.
- The expanded mobile filter area has a bounded, independently scrollable height.
- Filter dropdowns open as bottom sheets on mobile, preventing clipping inside the scrollable filter panel.
- Desktop filters remain expanded by default but can also be hidden.
- Pressing Escape closes an open mobile filter panel and open dropdowns.
- Pressing Search or Enter collapses the filter panel on mobile.

The filtering model, certification defaults, and feed payload are unchanged.
