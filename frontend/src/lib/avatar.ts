import { supabase } from './supabase'
import { apiPatch } from './api'

const BUCKET = 'avatars'

export interface AvatarMetadata {
  custom_avatar_url?: string | null
  avatar_url?: string | null
  picture?: string | null
}

// GitHub의 구 identicon 엔드포인트(github.com/identicons/<seed>.png)는 제공이 중단돼
// 404를 돌려준다(2025년 이후 확인). 동일한 픽셀 아트 스타일을 주는 DiceBear identicon API로 교체.
// PNG로 받아야 <img src>에 바로 꽂을 수 있다(SVG는 일부 환경에서 CORS/canvas 제약).
export function identiconUrl(seed: string): string {
  return `https://api.dicebear.com/9.x/identicon/png?seed=${encodeURIComponent(seed)}`
}

// 사용자가 직접 업로드한 custom_avatar_url 이 있으면 그것을 쓰고, 없으면 무조건
// GitHub identicon. OAuth(Google 등)가 채워준 avatar_url / picture 는 의도적으로
// 무시한다 — 기본 이미지를 GitHub identicon 으로 통일하기 위함.
export function resolveAvatarUrl(
  metadata: AvatarMetadata | undefined | null,
  seed: string,
): string {
  return metadata?.custom_avatar_url || identiconUrl(seed)
}

export async function uploadAvatar(file: File): Promise<string> {
  const { data: { user }, error: userErr } = await supabase.auth.getUser()
  if (userErr || !user) throw new Error('로그인이 필요합니다')

  const ext = (file.name.split('.').pop() || 'png').toLowerCase()
  const path = `${user.id}/avatar-${Date.now()}.${ext}`

  const { error: upErr } = await supabase.storage.from(BUCKET).upload(path, file, {
    upsert: true,
    contentType: file.type || 'image/png',
    cacheControl: '3600',
  })
  if (upErr) throw new Error(upErr.message)

  const { data: pub } = supabase.storage.from(BUCKET).getPublicUrl(path)

  const prevPath = extractStoragePath(
    (user.user_metadata as AvatarMetadata | undefined)?.custom_avatar_url,
  )
  if (prevPath && prevPath !== path) {
    await supabase.storage.from(BUCKET).remove([prevPath]).catch(() => undefined)
  }

  const { error: metaErr } = await supabase.auth.updateUser({
    data: { custom_avatar_url: pub.publicUrl },
  })
  if (metaErr) throw new Error(metaErr.message)

  // 백엔드 DB(UserRow.avatar_url)도 동기화 — 리더보드/최근 제출 등 타인 노출 화면은
  // Supabase user_metadata가 아니라 DB의 avatar_url을 읽기 때문에, 여기서 PATCH /me를
  // 안 하면 본인 화면에서는 새 이미지가 보여도 다른 사람에게는 식별 아바타가 안 뜬다.
  await apiPatch('/me', { avatar_url: pub.publicUrl })

  return pub.publicUrl
}

export async function resetAvatar(): Promise<void> {
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) throw new Error('로그인이 필요합니다')

  const prevPath = extractStoragePath(
    (user.user_metadata as AvatarMetadata | undefined)?.custom_avatar_url,
  )
  if (prevPath) {
    await supabase.storage.from(BUCKET).remove([prevPath]).catch(() => undefined)
  }

  const { error } = await supabase.auth.updateUser({
    data: { custom_avatar_url: null },
  })
  if (error) throw new Error(error.message)

  // DB의 avatar_url도 함께 비워야 리더보드에서 identicon fallback으로 떨어진다.
  await apiPatch('/me', { avatar_url: null })
}

// Supabase 공개 URL(`.../object/public/avatars/<path>`)에서 버킷 내부 경로 추출.
function extractStoragePath(url: string | null | undefined): string | null {
  if (!url) return null
  const marker = `/${BUCKET}/`
  const idx = url.indexOf(marker)
  if (idx < 0) return null
  return url.slice(idx + marker.length).split('?')[0]
}
