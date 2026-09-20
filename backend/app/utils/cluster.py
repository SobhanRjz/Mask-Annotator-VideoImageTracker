import numpy as np


CLUSTER_NAMES = {
    1: ['Typical'],
    2: ['Compact', 'Large'],
    3: ['Compact', 'Typical', 'Large'],
}


def kmeans_1d(values, k=3, rounds=24):
    samples = np.asarray(values, dtype=np.float64).reshape(-1)
    if samples.size == 0:
        return []
    unique = np.unique(np.round(samples, 6))
    k = max(1, min(int(k), unique.size, samples.size))
    centroids = np.quantile(samples, np.linspace(0, 1, k))
    assign = np.zeros(samples.size, dtype=np.int64)
    for _ in range(rounds):
        distances = np.abs(samples[:, None] - centroids[None, :])
        assign = distances.argmin(axis=1)
        updated = centroids.copy()
        for index in range(k):
            members = samples[assign == index]
            if members.size:
                updated[index] = members.mean()
        if np.allclose(updated, centroids):
            centroids = updated
            break
        centroids = updated
    distances = np.abs(samples[:, None] - centroids[None, :])
    assign = distances.argmin(axis=1)
    names = CLUSTER_NAMES.get(k, [f'Cluster {index + 1}' for index in range(k)])
    clusters = []
    for name, index in zip(names, np.argsort(centroids)):
        members = samples[assign == index]
        clusters.append({
            'label': name,
            'count': int(members.size),
            'mean_pixels': float(members.mean()) if members.size else 0.0,
            'share': float(members.size / samples.size) if samples.size else 0.0,
        })
    return clusters
