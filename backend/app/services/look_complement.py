from app.services.garment import filter_garments_for_part_role


class LookComplementService:
    def infer_missing_categories(
        self,
        part_results: list[dict],
        scene_hint: str | None = None,
        include_accessories: bool = False,
    ) -> list[str]:
        if not part_results:
            return []

        roles = {str(p.get("part_role") or "") for p in part_results}
        missing: list[str] = []

        if "top" in roles and "bottom" not in roles:
            missing.append("bottom")
        if {"top", "bottom"}.issubset(roles) and "shoes" not in roles:
            missing.append("shoes")

        scene = (scene_hint or "").lower()
        if {"commute", "formal", "business"} & {scene} or any(
            token in scene for token in ["通勤", "正式", "商务"]
        ):
            if "bag" not in roles:
                missing.append("bag")

        if include_accessories and {"top", "bottom"}.issubset(roles) and "accessory" not in roles:
            missing.append("accessory")

        return list(dict.fromkeys(missing))

    def recommend_missing_items(
        self,
        part_results: list[dict],
        wardrobe_garments: list,
        scene_hint: str | None = None,
        include_accessories: bool = False,
    ) -> list[dict]:
        missing = self.infer_missing_categories(
            part_results,
            scene_hint=scene_hint,
            include_accessories=include_accessories,
        )
        recommendations: list[dict] = []
        for role in missing:
            candidates = filter_garments_for_part_role(wardrobe_garments, role)
            for garment in candidates[:3]:
                recommendations.append(
                    {
                        "part_role": role,
                        "garment_id": str(getattr(garment, "garment_id", "")),
                        "name": getattr(garment, "name", None),
                        "category": getattr(garment, "category", ""),
                        "image_url": getattr(garment, "image_url", ""),
                        "reason": self._reason_for(role, scene_hint),
                    }
                )
        return recommendations

    def _reason_for(self, role: str, scene_hint: str | None) -> str:
        if role == "shoes":
            return "complete the top and bottom look"
        if role == "bag":
            return "fits commute or formal styling"
        if role == "accessory":
            return "adds styling detail"
        return "fills the missing look category"
