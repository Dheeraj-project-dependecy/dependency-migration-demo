stage('Build') {
    steps {
        bat 'mvn clean verify'
    }
}

stage('Dependency Migration Agent') {
    steps {
        bat 'python migration-agent\\run_agent.py'
    }
}