// gen_synthetic_data.cpp
//
// NOT part of the CS149 handout. This is a local helper added so that prog6
// (kmeans) can be run without access to the official dataset at
// <COURSE_DATA_PATH> (which is only mounted on the
// Stanford myth machines).
//
// It produces ./data.dat using exactly the synthetic-data path that main.cpp
// documents in its commented-out block: M = 1e6 points, N = 100 dimensions,
// K = 3 clusters, epsilon = 0.1, seed 7. The file format is the one written by
// utils.cpp:writeData(), so readData() consumes it unchanged.
//
// Build:  g++ -O2 -o gen_synthetic_data gen_synthetic_data.cpp utils.cpp
// Run  :  ./gen_synthetic_data.exe          (~800 MB, takes a few seconds)

#include <cstdio>
#include <cstdlib>
#include <random>
#include <string>

using namespace std;

extern void writeData(string filename, double *data, double *clusterCentroids,
                      int *clusterAssignments, int *M_p, int *N_p, int *K_p,
                      double *epsilon_p);

static double randDouble() {
  return static_cast<double>(rand()) / static_cast<double>(RAND_MAX);
}

// Same as main.cpp:initData()
static void initData(double *data, int M, int N) {
  int K = 10;
  double *centers = new double[K * N];

  double mean = 0.0;
  double stddev = 0.5;
  std::default_random_engine generator;
  std::normal_distribution<double> normal_dist(mean, stddev);

  for (int k = 0; k < K; k++) {
    for (int n = 0; n < N; n++) {
      centers[k * N + n] = randDouble();
    }
  }

  for (int m = 0; m < M; m++) {
    int startingPoint = rand() % K;
    for (int n = 0; n < N; n++) {
      double noise = normal_dist(generator);
      data[m * N + n] = centers[startingPoint * N + n] + noise;
    }
  }

  delete[] centers;
}

// Same as main.cpp:initCentroids()
static void initCentroids(double *clusterCentroids, int K, int N) {
  for (int n = 0; n < N; n++) {
    clusterCentroids[n] = randDouble();
  }
  for (int k = 1; k < K; k++) {
    for (int n = 0; n < N; n++) {
      clusterCentroids[k * N + n] =
          clusterCentroids[n] + (randDouble() - 0.5) * 0.1;
    }
  }
}

int main() {
  srand(7);  // same SEED as main.cpp

  int M = 1e6;
  int N = 100;
  int K = 3;
  double epsilon = 0.1;

  printf("generating synthetic data.dat: M=%d N=%d K=%d epsilon=%f\n", M, N, K,
         epsilon);

  double *data = new double[(size_t)M * N];
  double *clusterCentroids = new double[(size_t)K * N];
  int *clusterAssignments = new int[M];

  initData(data, M, N);
  initCentroids(clusterCentroids, K, N);

  for (int m = 0; m < M; m++) {
    clusterAssignments[m] = 0;
  }

  writeData("./data.dat", data, clusterCentroids, clusterAssignments, &M, &N,
            &K, &epsilon);

  printf("wrote ./data.dat\n");

  delete[] data;
  delete[] clusterCentroids;
  delete[] clusterAssignments;
  return 0;
}
