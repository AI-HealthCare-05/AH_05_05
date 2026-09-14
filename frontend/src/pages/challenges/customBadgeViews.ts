import type { CustomChallengeBadgeAward, CustomChallengeBadgeAwardListResponse } from '@/entities/custom-challenge';

export interface CustomBadgeView {
  badgeId: number;
  name: string;
  imagePath: string;
  awards: CustomChallengeBadgeAward[];
}

export function customBadgeViews(response: CustomChallengeBadgeAwardListResponse): CustomBadgeView[] {
  const byBadgeId = new Map<number, CustomBadgeView>();
  for (const badge of response.availableBadges ?? []) {
    byBadgeId.set(badge.id, { badgeId: badge.id, name: badge.name, imagePath: badge.imagePath, awards: [] });
  }
  const awards = [...response.items].sort((a, b) => Date.parse(b.awardedAt) - Date.parse(a.awardedAt) || b.id - a.id);
  for (const award of awards) {
    const view = byBadgeId.get(award.badgeId);
    if (view?.awards.length) view.awards.push(award);
    else byBadgeId.set(award.badgeId, {
      badgeId: award.badgeId, name: award.badgeName, imagePath: award.badgeImagePath, awards: [award],
    });
  }
  return [...byBadgeId.values()];
}
