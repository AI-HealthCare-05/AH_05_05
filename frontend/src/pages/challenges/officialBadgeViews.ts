import type {
  ChallengeCatalogItem,
  UserChallengeBadge,
} from '@/entities/challenge';

export interface OfficialBadgeView {
  id: number;
  name: string;
  description: string | null;
  imagePath: string;
  official: boolean;
  awards: UserChallengeBadge[];
}

export function officialBadgeViews(
  catalog: ChallengeCatalogItem[],
  userBadges: UserChallengeBadge[],
): OfficialBadgeView[] {
  const byId = new Map<number, OfficialBadgeView>();
  for (const item of catalog) {
    const badge = item.reward_badge;
    if (!badge || byId.has(badge.id)) continue;
    byId.set(badge.id, {
      id: badge.id,
      name: badge.name,
      description: badge.description,
      imagePath: badge.image_path,
      official: true,
      awards: [],
    });
  }
  for (const award of userBadges) {
    let view = byId.get(award.badge_id);
    if (!view) {
      view = {
        id: award.badge_id,
        name: award.badge_name,
        description: null,
        imagePath: award.badge_image_path,
        official: false,
        awards: [],
      };
      byId.set(award.badge_id, view);
    }
    if (award.status === 'AWARDED') view.awards.push(award);
  }
  return [...byId.values()];
}
