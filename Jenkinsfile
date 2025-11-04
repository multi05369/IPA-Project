pipeline {
  agent any

  options {
    timestamps()
    ansiColor('xterm')
  }

  environment {
    DOCKERHUB_NAMESPACE = 'taikie'
    FLAKE8_VERSION = '7.1.1'
    BLACK_VERSION = '24.8.0'
    PIP_CACHE_DIR = "${WORKSPACE}/.pip-cache"
    NPM_CACHE_DIR = "${WORKSPACE}/.npm-cache"
  }


  stages {

    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Lint & Format (Python 3.12)') {
      agent {
        docker {
          image 'python:3.12-slim'
          args "-v ${PIP_CACHE_DIR}:/root/.cache/pip"
          reuseNode true
        }
      }
      steps {
        sh '''
          python --version
          pip install --no-cache-dir flake8==${FLAKE8_VERSION} black==${BLACK_VERSION}
          flake8 .
          black --check .
        '''
      }
    }

    stage('Docker Login') {
      steps {
        sh '''
          docker --version
          docker compose version || true
        '''
        withCredentials([usernamePassword(credentialsId: 'c9a3ce30-d24d-4e56-8293-122ec8b53d25',
                                          usernameVariable: 'DOCKERHUB_USERNAME',
                                          passwordVariable: 'DOCKERHUB_TOKEN')]) {
          sh '''
            echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin
          '''
        }
      }
    }

    stage('Build Images') {
      steps {
        sh '''
          set -e
          docker build -t ${DOCKERHUB_NAMESPACE}/worker:latest ./worker
          docker build -t ${DOCKERHUB_NAMESPACE}/scheduler:latest ./scheduler
          docker build -t ${DOCKERHUB_NAMESPACE}/web:latest ./web
        '''
      }
    }

    stage('Push Images') {
      when {
        anyOf {
          branch 'main'
        }
      }
      steps {
        sh '''
          docker push ${DOCKERHUB_NAMESPACE}/worker:latest
          docker push ${DOCKERHUB_NAMESPACE}/scheduler:latest
          docker push ${DOCKERHUB_NAMESPACE}/web:latest
        '''
      }
    }
  }

  post {
    always {
      sh 'docker logout || true'
    }
    success {
      echo 'CI passed. Images built (and pushed if on main).'
    }
    failure {
      echo 'CI failed. Check lint or build logs.'
    }
  }
}