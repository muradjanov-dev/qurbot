import time
from decimal import Decimal
from itertools import combinations
from typing import Any

from app.core.exceptions import DomainException
from app.domain.models import OfferPricing
from app.domain.optimizer.delivery import calculate_shop_delivery_fee
from app.domain.optimizer.haversine import haversine_km
from app.domain.optimizer.models import (
    BasketItemQuery,
    DeliveryTier,
    LineAssignment,
    OptimizationResult,
    OptimizationStrategy,
    QuoteVariant,
    ShopOffer,
    ShopQuoteGroup,
)
from app.domain.pricing.units import line_cost, unit_price


class BasketOptimizer:
    """Pure domain basket optimization engine with exact and heuristic algorithms."""

    def __init__(
        self,
        basket_items: list[BasketItemQuery],
        offers: list[ShopOffer],
        delivery_rules: dict[int, DeliveryTier],
        customer_lat: float | None = None,
        customer_lon: float | None = None,
    ) -> None:
        self.basket_items = sorted(basket_items, key=lambda x: x.line_no)
        self.all_offers = offers
        self.delivery_rules = delivery_rules
        self.customer_lat = customer_lat
        self.customer_lon = customer_lon

        # Pre-filter active & non-stale offers
        available = [
            o
            for o in self.all_offers
            if o.is_active
            and o.staleness_state != "stale"
            and o.stock_status in ("in_stock", "low", "on_order")
        ]
        self.valid_offers = self._filter_by_stock(available)

    def _filter_by_stock(self, offers: list[ShopOffer]) -> list[ShopOffer]:
        """Drop offers that cannot cover what the customer asked for.

        Quoting a shop that holds three bags against an order for ten produces a
        price the shop cannot honour, so those offers are removed outright.

        When *no* shop can cover a line, the ones holding the most are kept
        instead of dropping the line entirely: a customer who needs 100 and can
        be shown the shop with 40 is better served than one shown nothing, and
        the line would otherwise be reported as uncovered. Ties are kept whole so
        the optimizer still picks the cheapest among equally-stocked shops, which
        also keeps the result deterministic regardless of input order.
        """
        offers_by_canonical: dict[int, list[ShopOffer]] = {}
        for offer in offers:
            offers_by_canonical.setdefault(offer.canonical_id, []).append(offer)

        keep_ids: set[int] = set()
        constrained_canonicals: set[int] = set()

        for item in self.basket_items:
            candidates = offers_by_canonical.get(item.canonical_id, [])
            if not candidates:
                continue
            constrained_canonicals.add(item.canonical_id)

            sufficient = [o for o in candidates if self._can_cover(item, o)]
            if sufficient:
                keep_ids.update(o.offer_id for o in sufficient)
                continue

            best_stock = max((o.stock_qty or Decimal("0")) for o in candidates)
            if best_stock <= Decimal("0"):
                # Nobody holds any of it: leave the line genuinely uncovered
                # rather than quoting a shop with an empty shelf.
                continue
            keep_ids.update(
                o.offer_id for o in candidates if (o.stock_qty or Decimal("0")) == best_stock
            )

        return [
            o
            for o in offers
            if o.canonical_id not in constrained_canonicals or o.offer_id in keep_ids
        ]

    def _can_cover(self, item: BasketItemQuery, offer: ShopOffer) -> bool:
        """Whether this offer holds enough packs for the line, after pack rounding."""
        if offer.stock_qty is None:
            return True
        try:
            packs_needed = self._compute_line_assignment(item, offer).packs_needed
        except DomainException:
            # A unit mismatch is a matching problem, not a stock one -- leave the
            # offer in and let the existing pricing path report it.
            return True
        return offer.stock_qty >= Decimal(str(packs_needed))

    def solve(self) -> OptimizationResult:
        start_time = time.perf_counter()

        if not self.basket_items or not self.valid_offers:
            empty_variant = self._create_empty_variant(OptimizationStrategy.CHEAPEST_TOTAL)
            return OptimizationResult(
                variants=(empty_variant,),
                deduplicated_variants=(empty_variant,),
                total_candidate_shops=0,
                total_offers_evaluated=len(self.all_offers),
                solve_duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        # 1. Evaluate individual strategy solutions
        cheapest_sol = self._solve_cheapest_total()
        single_sol = self._solve_single_shop()
        fastest_sol = self._solve_fastest()
        premium_sol = self._solve_premium()

        candidate_pool = [cheapest_sol, single_sol, fastest_sol, premium_sol]
        balanced_sol = self._solve_balanced(candidate_pool)

        # 2. Build full variants list
        raw_variants: list[QuoteVariant] = [
            self._build_variant((OptimizationStrategy.CHEAPEST_TOTAL,), cheapest_sol),
            self._build_variant((OptimizationStrategy.SINGLE_SHOP,), single_sol),
            self._build_variant((OptimizationStrategy.FASTEST,), fastest_sol),
            self._build_variant((OptimizationStrategy.PREMIUM,), premium_sol),
            self._build_variant((OptimizationStrategy.BALANCED,), balanced_sol),
        ]

        # 3. Calculate savings vs worst
        worst_total = max((v.grand_total_uzs for v in raw_variants), default=Decimal("0"))
        updated_variants: list[QuoteVariant] = []
        for v in raw_variants:
            savings = max(Decimal("0"), worst_total - v.grand_total_uzs)
            savings_pct = (
                float(savings / worst_total * Decimal("100")) if worst_total > Decimal("0") else 0.0
            )
            updated_variants.append(
                QuoteVariant(
                    strategy_labels=v.strategy_labels,
                    shop_groups=v.shop_groups,
                    items_total_uzs=v.items_total_uzs,
                    delivery_total_uzs=v.delivery_total_uzs,
                    grand_total_uzs=v.grand_total_uzs,
                    coverage_pct=v.coverage_pct,
                    covered_count=v.covered_count,
                    total_count=v.total_count,
                    missing_lines=v.missing_lines,
                    savings_vs_worst_uzs=savings,
                    savings_pct=round(savings_pct, 1),
                    max_eta_hours=v.max_eta_hours,
                    composite_score=v.composite_score,
                )
            )

        # 4. Deduplicate variants
        deduplicated = self._deduplicate_variants(updated_variants)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        unique_candidate_shops = len({o.shop_id for o in self.valid_offers})

        return OptimizationResult(
            variants=tuple(updated_variants),
            deduplicated_variants=tuple(deduplicated),
            total_candidate_shops=unique_candidate_shops,
            total_offers_evaluated=len(self.all_offers),
            solve_duration_ms=duration_ms,
        )

    # -------------------------------------------------------------------------
    # Core Strategy Solvers
    # -------------------------------------------------------------------------

    def _solve_cheapest_total(self) -> dict[str, Any]:
        """Minimize landed total = sum(line_costs) + sum(delivery_fees)."""
        offers_by_item = self._group_offers_by_item(self.valid_offers)
        candidate_shops = sorted(list({o.shop_id for o in self.valid_offers}))

        # If candidate pool <= 12, use exact brute-force subset enumeration
        if len(candidate_shops) <= 12:
            return self._exact_subset_solver(offers_by_item, candidate_shops)

        # Otherwise, greedy construction + local search
        return self._greedy_local_search_solver(offers_by_item, candidate_shops)

    def _solve_single_shop(self) -> dict[str, Any]:
        """Find the single shop that maximizes coverage, then minimizes cost."""
        offers_by_shop: dict[int, list[ShopOffer]] = {}
        for o in self.valid_offers:
            offers_by_shop.setdefault(o.shop_id, []).append(o)

        best_solution: dict[str, Any] | None = None

        for shop_id, shop_offers in sorted(offers_by_shop.items()):
            shop_item_map = {o.canonical_id: o for o in shop_offers}
            assignments: list[LineAssignment] = []
            missing: list[BasketItemQuery] = []

            for item in self.basket_items:
                offer = shop_item_map.get(item.canonical_id)
                if offer:
                    asgn = self._compute_line_assignment(item, offer)
                    assignments.append(asgn)
                else:
                    missing.append(item)

            if not assignments:
                continue

            subtotal = sum((a.line_cost_uzs for a in assignments), Decimal("0"))
            rule = self.delivery_rules.get(shop_id)
            fee, is_free, is_eligible = calculate_shop_delivery_fee(rule, subtotal)
            grand_total = subtotal + fee

            sol = {
                "assignments": assignments,
                "missing": missing,
                "subtotal": subtotal,
                "delivery_fee": fee,
                "grand_total": grand_total,
                "coverage_count": len(assignments),
                "used_shops": {shop_id},
                "avg_trust": shop_offers[0].trust_score,
                "max_eta": shop_offers[0].eta_hours,
                "is_eligible": is_eligible,
            }

            if best_solution is None or self._is_better_solution(sol, best_solution):
                best_solution = sol

        if best_solution is None:
            return self._create_empty_solution()

        return best_solution

    def _solve_fastest(self) -> dict[str, Any]:
        """Only in_stock + eta_hours <= 24, then cheapest."""
        fast_offers = [o for o in self.valid_offers if o.in_stock and o.eta_hours <= 24]
        if not fast_offers:
            # Fallback to offers with lowest available eta
            min_eta = min((o.eta_hours for o in self.valid_offers), default=48)
            fast_offers = [o for o in self.valid_offers if o.eta_hours <= min_eta]

        offers_by_item = self._group_offers_by_item(fast_offers)
        candidate_shops = sorted(list({o.shop_id for o in fast_offers}))

        if len(candidate_shops) <= 12:
            return self._exact_subset_solver(offers_by_item, candidate_shops)
        return self._greedy_local_search_solver(offers_by_item, candidate_shops)

    def _solve_premium(self) -> dict[str, Any]:
        """Prefer tier='premium' or known brands, then cheapest."""
        # Score offers: premium tier gets 0.8 weight discount for selection
        sorted_offers = sorted(
            self.valid_offers,
            key=lambda o: (0 if o.tier == "premium" else (1 if o.brand_name else 2), o.price_uzs),
        )
        offers_by_item = self._group_offers_by_item(sorted_offers)
        candidate_shops = sorted(list({o.shop_id for o in sorted_offers}))

        if len(candidate_shops) <= 12:
            return self._exact_subset_solver(offers_by_item, candidate_shops)
        return self._greedy_local_search_solver(offers_by_item, candidate_shops)

    def _solve_balanced(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """Minimize weighted score of min-max normalized metrics:

        Score = 0.45 * Cost_norm + 0.20 * ETA_norm + 0.20 * (1 - Trust_norm) + 0.15 * Shops_norm
        """
        valid_candidates = [c for c in candidates if c.get("assignments")]
        if not valid_candidates:
            return self._create_empty_solution()

        costs = [float(c["grand_total"]) for c in valid_candidates]
        etas = [float(c["max_eta"]) for c in valid_candidates]
        trusts = [float(c["avg_trust"]) for c in valid_candidates]
        shops_counts = [float(len(c["used_shops"])) for c in valid_candidates]

        min_c, max_c = min(costs), max(costs)
        min_e, max_e = min(etas), max(etas)
        min_t, max_t = min(trusts), max(trusts)
        min_s, max_s = min(shops_counts), max(shops_counts)

        eps = 1e-9

        best_score = float("inf")
        best_sol = valid_candidates[0]

        for c in valid_candidates:
            c_norm = (float(c["grand_total"]) - min_c) / (max_c - min_c + eps)
            e_norm = (float(c["max_eta"]) - min_e) / (max_e - min_e + eps)
            t_norm = (float(c["avg_trust"]) - min_t) / (max_t - min_t + eps)
            s_norm = (float(len(c["used_shops"])) - min_s) / (max_s - min_s + eps)

            score = 0.45 * c_norm + 0.20 * e_norm + 0.20 * (1.0 - t_norm) + 0.15 * s_norm
            c["composite_score"] = round(score, 4)

            if score < best_score:
                best_score = score
                best_sol = c

        return best_sol

    # -------------------------------------------------------------------------
    # Exact & Heuristic Optimization Algorithms
    # -------------------------------------------------------------------------

    def _exact_subset_solver(
        self,
        offers_by_item: dict[int, list[ShopOffer]],
        candidate_shops: list[int],
    ) -> dict[str, Any]:
        """Exact brute force enumeration of shop subsets (for candidate_shops <= 12)."""
        best_solution: dict[str, Any] | None = None
        max_k = min(len(candidate_shops), 4)  # Practical order splitting upper bound is 4 shops

        # Test all shop subsets of size 1, 2, 3, up to max_k
        for k in range(1, max_k + 1):
            for shop_subset in combinations(candidate_shops, k):
                active_shop_set = set(shop_subset)
                assignments: list[LineAssignment] = []
                missing: list[BasketItemQuery] = []

                for item in self.basket_items:
                    item_offers = [
                        o
                        for o in offers_by_item.get(item.canonical_id, [])
                        if o.shop_id in active_shop_set
                    ]
                    if not item_offers:
                        missing.append(item)
                        continue

                    # Select cheapest offer among active shops
                    best_offer_asgn = min(
                        (self._compute_line_assignment(item, o) for o in item_offers),
                        key=lambda a: a.line_cost_uzs,
                    )
                    assignments.append(best_offer_asgn)

                if not assignments:
                    continue

                # Compute totals and delivery
                shops_used = {a.shop_id for a in assignments}
                items_subtotal = Decimal("0")
                delivery_total = Decimal("0")
                is_all_eligible = True
                shop_trusts: list[float] = []
                shop_etas: list[int] = []

                for s_id in sorted(shops_used):
                    s_lines = [a for a in assignments if a.shop_id == s_id]
                    s_subtotal = sum((a.line_cost_uzs for a in s_lines), Decimal("0"))
                    items_subtotal += s_subtotal

                    rule = self.delivery_rules.get(s_id)
                    fee, _, is_elig = calculate_shop_delivery_fee(rule, s_subtotal)
                    delivery_total += fee
                    if not is_elig:
                        is_all_eligible = False

                    # Representative offer metadata
                    rep_offer = next(o for o in self.valid_offers if o.shop_id == s_id)
                    shop_trusts.append(rep_offer.trust_score)
                    shop_etas.append(rep_offer.eta_hours)

                grand_total = items_subtotal + delivery_total

                sol = {
                    "assignments": assignments,
                    "missing": missing,
                    "subtotal": items_subtotal,
                    "delivery_fee": delivery_total,
                    "grand_total": grand_total,
                    "coverage_count": len(assignments),
                    "used_shops": shops_used,
                    "avg_trust": sum(shop_trusts) / len(shop_trusts) if shop_trusts else 0.0,
                    "max_eta": max(shop_etas) if shop_etas else 0,
                    "is_eligible": is_all_eligible,
                }

                if best_solution is None or self._is_better_solution(sol, best_solution):
                    best_solution = sol

        return best_solution if best_solution is not None else self._create_empty_solution()

    def _greedy_local_search_solver(
        self,
        offers_by_item: dict[int, list[ShopOffer]],
        candidate_shops: list[int],
    ) -> dict[str, Any]:
        """Greedy construction + local search (reassign, drop, swap) with 200 iteration limit."""
        # 1. Greedy construction: start with best single shop
        current_sol = self._solve_single_shop()
        if not current_sol.get("assignments"):
            # Fallback if single shop fails
            return self._exact_subset_solver(offers_by_item, candidate_shops[:10])

        used_shops = set(current_sol["used_shops"])

        # Repeatedly add shops that give positive marginal saving
        for _ in range(5):
            best_addition: int | None = None
            best_saving = Decimal("0")

            for shop_id in candidate_shops:
                if shop_id in used_shops:
                    continue

                test_shops = used_shops | {shop_id}
                test_sol = self._evaluate_shop_set(offers_by_item, test_shops)
                if test_sol and test_sol["grand_total"] < current_sol["grand_total"]:
                    saving = current_sol["grand_total"] - test_sol["grand_total"]
                    if saving > best_saving:
                        best_saving = saving
                        best_addition = shop_id

            if best_addition is not None:
                used_shops.add(best_addition)
                current_sol = self._evaluate_shop_set(offers_by_item, used_shops)
            else:
                break

        # 2. Local Search: reassign, drop, swap
        for _ in range(200):
            improved = False

            # Drop move
            if len(used_shops) > 1:
                for shop_to_drop in list(used_shops):
                    reduced_shops = used_shops - {shop_to_drop}
                    reduced_sol = self._evaluate_shop_set(offers_by_item, reduced_shops)
                    if (
                        reduced_sol
                        and reduced_sol["coverage_count"] >= current_sol["coverage_count"]
                        and reduced_sol["grand_total"] < current_sol["grand_total"]
                    ):
                        used_shops = reduced_shops
                        current_sol = reduced_sol
                        improved = True
                        break

            if improved:
                continue

            # Swap move
            for used_s in list(used_shops):
                for unused_s in candidate_shops:
                    if unused_s in used_shops:
                        continue
                    swapped_shops = (used_shops - {used_s}) | {unused_s}
                    swapped_sol = self._evaluate_shop_set(offers_by_item, swapped_shops)
                    if (
                        swapped_sol
                        and swapped_sol["coverage_count"] >= current_sol["coverage_count"]
                        and swapped_sol["grand_total"] < current_sol["grand_total"]
                    ):
                        used_shops = swapped_shops
                        current_sol = swapped_sol
                        improved = True
                        break
                if improved:
                    break

            if not improved:
                break

        return current_sol

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _evaluate_shop_set(
        self,
        offers_by_item: dict[int, list[ShopOffer]],
        shop_set: set[int],
    ) -> dict[str, Any]:
        assignments: list[LineAssignment] = []
        missing: list[BasketItemQuery] = []

        for item in self.basket_items:
            item_offers = [
                o for o in offers_by_item.get(item.canonical_id, []) if o.shop_id in shop_set
            ]
            if not item_offers:
                missing.append(item)
                continue

            best_asgn = min(
                (self._compute_line_assignment(item, o) for o in item_offers),
                key=lambda a: a.line_cost_uzs,
            )
            assignments.append(best_asgn)

        if not assignments:
            return self._create_empty_solution()

        actual_used_shops = {a.shop_id for a in assignments}
        items_subtotal = Decimal("0")
        delivery_total = Decimal("0")
        shop_trusts: list[float] = []
        shop_etas: list[int] = []

        for s_id in sorted(actual_used_shops):
            s_lines = [a for a in assignments if a.shop_id == s_id]
            s_subtotal = sum((a.line_cost_uzs for a in s_lines), Decimal("0"))
            items_subtotal += s_subtotal

            rule = self.delivery_rules.get(s_id)
            fee, _, is_elig = calculate_shop_delivery_fee(rule, s_subtotal)
            delivery_total += fee

            rep_offer = next(o for o in self.valid_offers if o.shop_id == s_id)
            shop_trusts.append(rep_offer.trust_score)
            shop_etas.append(rep_offer.eta_hours)

        grand_total = items_subtotal + delivery_total

        return {
            "assignments": assignments,
            "missing": missing,
            "subtotal": items_subtotal,
            "delivery_fee": delivery_total,
            "grand_total": grand_total,
            "coverage_count": len(assignments),
            "used_shops": actual_used_shops,
            "avg_trust": sum(shop_trusts) / len(shop_trusts) if shop_trusts else 0.0,
            "max_eta": max(shop_etas) if shop_etas else 0,
            "is_eligible": True,
        }

    def _is_better_solution(self, cand: dict[str, Any], best: dict[str, Any]) -> bool:
        """Deterministic tie-breaking comparator."""
        # 1. Coverage count (maximize)
        if cand["coverage_count"] != best["coverage_count"]:
            return bool(cand["coverage_count"] > best["coverage_count"])

        # 2. Grand total (minimize)
        if cand["grand_total"] != best["grand_total"]:
            return bool(cand["grand_total"] < best["grand_total"])

        # 3. Number of shops used (minimize)
        if len(cand["used_shops"]) != len(best["used_shops"]):
            return bool(len(cand["used_shops"]) < len(best["used_shops"]))

        # 4. Avg trust score (maximize)
        if cand["avg_trust"] != best["avg_trust"]:
            return bool(cand["avg_trust"] > best["avg_trust"])

        # 5. Deterministic tie breaker: min shop_id
        cand_min_id = min(cand["used_shops"]) if cand["used_shops"] else 0
        best_min_id = min(best["used_shops"]) if best["used_shops"] else 0
        return bool(cand_min_id < best_min_id)

    def _price_line(
        self, item: BasketItemQuery, offer: ShopOffer, price_per_pack: Decimal
    ) -> tuple[Any, Decimal]:
        """Cost this line at a given per-pack price. Returns (cost, unit price)."""
        price_per_base = (
            (price_per_pack / offer.pack_size) if offer.pack_size > Decimal("0") else price_per_pack
        )
        offer_pricing = OfferPricing(
            shop_product_id=offer.offer_id,
            shop_id=offer.shop_id,
            canonical_id=offer.canonical_id,
            raw_name=offer.shop_name,
            pack_size=offer.pack_size,
            pack_unit=offer.pack_unit,
            price_per_pack=price_per_pack,
            price_per_base_unit=price_per_base,
        )
        cost_calc = line_cost(
            required_qty=item.needed_qty,
            required_unit=item.unit_code,
            offer=offer_pricing,
        )
        u_price = unit_price(
            pack_size=offer.pack_size,
            pack_unit=offer.pack_unit,
            price_per_pack=price_per_pack,
            base_unit=item.unit_code,
        )
        return cost_calc, u_price

    def _compute_line_assignment(self, item: BasketItemQuery, offer: ShopOffer) -> LineAssignment:
        cost_calc, u_price = self._price_line(item, offer, offer.price_uzs)

        # How many packs are needed does not depend on the price, so the volume
        # price is resolved once that is known and the line is costed again.
        # Wholesale is quoted as a threshold ("10$ from 200 sheets"), and a
        # customer ordering a lorry-load must not be billed the retail price.
        if offer.price_tiers:
            tier_price = offer.price_for_packs(Decimal(cost_calc.packs_needed))
            if tier_price != offer.price_uzs:
                cost_calc, u_price = self._price_line(item, offer, tier_price)
        return LineAssignment(
            line_no=item.line_no,
            canonical_id=item.canonical_id,
            product_name=item.name_uz,
            shop_id=offer.shop_id,
            shop_name=offer.shop_name,
            offer_id=offer.offer_id,
            needed_qty=item.needed_qty,
            needed_unit=item.unit_code,
            pack_size=offer.pack_size,
            pack_unit=offer.pack_unit,
            packs_needed=cost_calc.packs_needed,
            billed_qty=cost_calc.billed_qty,
            overage_qty=cost_calc.overage_qty,
            unit_price_uzs=u_price,
            line_cost_uzs=cost_calc.cost,
        )

    def _group_offers_by_item(self, offers: list[ShopOffer]) -> dict[int, list[ShopOffer]]:
        grouped: dict[int, list[ShopOffer]] = {}
        for o in offers:
            grouped.setdefault(o.canonical_id, []).append(o)
        return grouped

    def _build_variant(
        self,
        labels: tuple[OptimizationStrategy, ...],
        sol: dict[str, Any],
    ) -> QuoteVariant:
        assignments: list[LineAssignment] = sol.get("assignments", [])
        missing: list[BasketItemQuery] = sol.get("missing", [])
        covered_count = len(assignments)
        total_count = len(self.basket_items)
        coverage_pct = round((covered_count / total_count * 100.0) if total_count > 0 else 0.0, 1)

        # Build ShopQuoteGroups
        groups: list[ShopQuoteGroup] = []
        shop_ids = sorted(list({a.shop_id for a in assignments}))

        for s_id in shop_ids:
            s_lines = tuple(a for a in assignments if a.shop_id == s_id)
            s_subtotal = sum((a.line_cost_uzs for a in s_lines), Decimal("0"))
            rule = self.delivery_rules.get(s_id)
            fee, is_free, _ = calculate_shop_delivery_fee(rule, s_subtotal)

            rep_offer = next(o for o in self.valid_offers if o.shop_id == s_id)
            dist_km = haversine_km(
                self.customer_lat, self.customer_lon, rep_offer.lat, rep_offer.lon
            )

            groups.append(
                ShopQuoteGroup(
                    shop_id=s_id,
                    shop_name=rep_offer.shop_name,
                    district_name=None,
                    distance_km=dist_km,
                    lines=s_lines,
                    subtotal_uzs=s_subtotal,
                    delivery_fee_uzs=fee,
                    is_free_delivery=is_free,
                    eta_hours=rep_offer.eta_hours,
                    trust_score=rep_offer.trust_score,
                )
            )

        items_total = sum((g.subtotal_uzs for g in groups), Decimal("0"))
        delivery_total = sum((g.delivery_fee_uzs for g in groups), Decimal("0"))
        grand_total = items_total + delivery_total
        max_eta = max((g.eta_hours for g in groups), default=0)

        return QuoteVariant(
            strategy_labels=labels,
            shop_groups=tuple(groups),
            items_total_uzs=items_total,
            delivery_total_uzs=delivery_total,
            grand_total_uzs=grand_total,
            coverage_pct=coverage_pct,
            covered_count=covered_count,
            total_count=total_count,
            missing_lines=tuple(missing),
            savings_vs_worst_uzs=Decimal("0"),
            savings_pct=0.0,
            max_eta_hours=max_eta,
            composite_score=sol.get("composite_score", 0.0),
        )

    def _deduplicate_variants(self, variants: list[QuoteVariant]) -> list[QuoteVariant]:
        """Merge variants with identical shop assignments into one presentation card."""
        dedup_map: dict[tuple[tuple[int, int], ...], QuoteVariant] = {}

        for v in variants:
            signature = tuple(
                sorted((line.line_no, line.shop_id) for g in v.shop_groups for line in g.lines)
            )
            if signature not in dedup_map:
                dedup_map[signature] = v
            else:
                existing = dedup_map[signature]
                merged_labels = tuple(dict.fromkeys(existing.strategy_labels + v.strategy_labels))
                dedup_map[signature] = QuoteVariant(
                    strategy_labels=merged_labels,
                    shop_groups=existing.shop_groups,
                    items_total_uzs=existing.items_total_uzs,
                    delivery_total_uzs=existing.delivery_total_uzs,
                    grand_total_uzs=existing.grand_total_uzs,
                    coverage_pct=existing.coverage_pct,
                    covered_count=existing.covered_count,
                    total_count=existing.total_count,
                    missing_lines=existing.missing_lines,
                    savings_vs_worst_uzs=existing.savings_vs_worst_uzs,
                    savings_pct=existing.savings_pct,
                    max_eta_hours=existing.max_eta_hours,
                    composite_score=existing.composite_score,
                )

        return list(dedup_map.values())

    def _create_empty_solution(self) -> dict[str, Any]:
        return {
            "assignments": [],
            "missing": self.basket_items,
            "subtotal": Decimal("0"),
            "delivery_fee": Decimal("0"),
            "grand_total": Decimal("0"),
            "coverage_count": 0,
            "used_shops": set(),
            "avg_trust": 0.0,
            "max_eta": 0,
            "is_eligible": True,
        }

    def _create_empty_variant(self, strategy: OptimizationStrategy) -> QuoteVariant:
        return QuoteVariant(
            strategy_labels=(strategy,),
            shop_groups=(),
            items_total_uzs=Decimal("0"),
            delivery_total_uzs=Decimal("0"),
            grand_total_uzs=Decimal("0"),
            coverage_pct=0.0,
            covered_count=0,
            total_count=len(self.basket_items),
            missing_lines=tuple(self.basket_items),
            savings_vs_worst_uzs=Decimal("0"),
            savings_pct=0.0,
            max_eta_hours=0,
        )
