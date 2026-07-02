import type {Movie} from "@/api/movie/types";

export function getMovieMagnetLinks(movie: Movie): string[] {
    const magnetLinks = Array.isArray(movie.magnets)
        ? movie.magnets.map((m) => m.magnet).filter((m): m is string => Boolean(m?.trim()))
        : [];
    if (magnetLinks.length > 0) return magnetLinks;
    return movie.magnet ? [movie.magnet] : [];
}
