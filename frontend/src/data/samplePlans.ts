import type { SamplePlanOption } from '../types';

export const SAMPLE_PLANS: SamplePlanOption[] = [
  {
    id: 'db-cascade',
    label: 'Database Deletion (Cascade)',
    description: 'Destruction of primary RDS database causing downstream outage to ECS API & DNS.',
    tag: 'BLOCKED (Score: 100)',
    tagColor: '#ef4444',
    jsonContent: JSON.stringify(
      {
        format_version: '1.2',
        terraform_version: '1.5.7',
        resource_changes: [
          {
            address: 'aws_db_instance.primary',
            mode: 'managed',
            type: 'aws_db_instance',
            name: 'primary',
            provider_name: 'registry.terraform.io/hashicorp/aws',
            change: {
              actions: ['delete'],
              before: {
                identifier: 'prod-mysql-primary',
                instance_class: 'db.r6g.xlarge',
                engine: 'mysql',
                allocated_storage: 100,
                deletion_protection: false,
              },
              after: null,
            },
          },
          {
            address: 'aws_ecs_service.api',
            mode: 'managed',
            type: 'aws_ecs_service',
            name: 'api',
            provider_name: 'registry.terraform.io/hashicorp/aws',
            change: {
              actions: ['no-op'],
              before: { name: 'api-service', desired_count: 3 },
              after: { name: 'api-service', desired_count: 3 },
            },
          },
          {
            address: 'aws_route53_record.db',
            mode: 'managed',
            type: 'aws_route53_record',
            name: 'db',
            provider_name: 'registry.terraform.io/hashicorp/aws',
            change: {
              actions: ['no-op'],
              before: { name: 'db.prod.internal', type: 'CNAME' },
              after: { name: 'db.prod.internal', type: 'CNAME' },
            },
          },
        ],
        configuration: {
          root_module: {
            resources: [
              {
                address: 'aws_db_instance.primary',
                mode: 'managed',
                type: 'aws_db_instance',
                name: 'primary',
              },
              {
                address: 'aws_ecs_service.api',
                mode: 'managed',
                type: 'aws_ecs_service',
                name: 'api',
                depends_on: ['aws_db_instance.primary'],
              },
              {
                address: 'aws_route53_record.db',
                mode: 'managed',
                type: 'aws_route53_record',
                name: 'db',
                expressions: {
                  records: {
                    references: ['aws_db_instance.primary.endpoint'],
                  },
                },
              },
            ],
          },
        },
      },
      null,
      2
    ),
  },
  {
    id: 'subnet-replace',
    label: 'Subnet Replacement (Multi-Tier)',
    description: 'Replacement of VPC private subnet cascading to EC2 app instance and ALB attachment.',
    tag: 'REVIEW_REQUIRED (Score: 35)',
    tagColor: '#f59e0b',
    jsonContent: JSON.stringify(
      {
        format_version: '1.2',
        terraform_version: '1.5.7',
        resource_changes: [
          {
            address: 'aws_subnet.private_app',
            mode: 'managed',
            type: 'aws_subnet',
            name: 'private_app',
            provider_name: 'registry.terraform.io/hashicorp/aws',
            change: {
              actions: ['delete', 'create'],
              before: {
                id: 'subnet-0a1b2c3d',
                cidr_block: '10.0.1.0/24',
                availability_zone: 'us-east-1a',
              },
              after: {
                cidr_block: '10.0.10.0/24',
                availability_zone: 'us-east-1a',
              },
              replace_paths: [['cidr_block']],
            },
          },
          {
            address: 'aws_instance.app_server',
            mode: 'managed',
            type: 'aws_instance',
            name: 'app_server',
            provider_name: 'registry.terraform.io/hashicorp/aws',
            change: {
              actions: ['no-op'],
              before: { id: 'i-0123456789abcdef0', instance_type: 't3.medium' },
              after: { id: 'i-0123456789abcdef0', instance_type: 't3.medium' },
            },
          },
          {
            address: 'aws_lb_target_group_attachment.tg_attachment',
            mode: 'managed',
            type: 'aws_lb_target_group_attachment',
            name: 'tg_attachment',
            provider_name: 'registry.terraform.io/hashicorp/aws',
            change: {
              actions: ['no-op'],
              before: { target_id: 'i-0123456789abcdef0', port: 8080 },
              after: { target_id: 'i-0123456789abcdef0', port: 8080 },
            },
          },
        ],
        configuration: {
          root_module: {
            resources: [
              {
                address: 'aws_subnet.private_app',
                mode: 'managed',
                type: 'aws_subnet',
                name: 'private_app',
              },
              {
                address: 'aws_instance.app_server',
                mode: 'managed',
                type: 'aws_instance',
                name: 'app_server',
                expressions: {
                  subnet_id: {
                    references: ['aws_subnet.private_app.id'],
                  },
                },
              },
              {
                address: 'aws_lb_target_group_attachment.tg_attachment',
                mode: 'managed',
                type: 'aws_lb_target_group_attachment',
                name: 'tg_attachment',
                expressions: {
                  target_id: {
                    references: ['aws_instance.app_server.id'],
                  },
                },
              },
            ],
          },
        },
      },
      null,
      2
    ),
  },
  {
    id: 'safe-add',
    label: 'Safe Resource Addition',
    description: 'Clean addition of audit logging S3 bucket with zero dependent impact.',
    tag: 'PASS (Score: 0)',
    tagColor: '#10b981',
    jsonContent: JSON.stringify(
      {
        format_version: '1.2',
        terraform_version: '1.5.7',
        resource_changes: [
          {
            address: 'aws_s3_bucket.logs',
            mode: 'managed',
            type: 'aws_s3_bucket',
            name: 'logs',
            provider_name: 'registry.terraform.io/hashicorp/aws',
            change: {
              actions: ['create'],
              before: null,
              after: {
                bucket: 'app-logs-prod-audit',
                force_destroy: false,
                tags: { Environment: 'production' },
              },
              after_unknown: { id: true, arn: true },
            },
          },
        ],
        configuration: {
          root_module: {
            resources: [
              {
                address: 'aws_s3_bucket.logs',
                mode: 'managed',
                type: 'aws_s3_bucket',
                name: 'logs',
                provider_config_key: 'aws',
              },
            ],
          },
        },
      },
      null,
      2
    ),
  },
  {
    id: 'cyclic-graph',
    label: 'Cyclic Security Groups',
    description: 'Bidirectional security group reference forming a circular graph topology.',
    tag: 'CYCLE DETECTED (Score: 20)',
    tagColor: '#8b5cf6',
    jsonContent: JSON.stringify(
      {
        format_version: '1.2',
        terraform_version: '1.5.7',
        resource_changes: [
          {
            address: 'aws_security_group.sg_a',
            mode: 'managed',
            type: 'aws_security_group',
            name: 'sg_a',
            provider_name: 'registry.terraform.io/hashicorp/aws',
            change: {
              actions: ['update'],
              before: { name: 'sg-a' },
              after: { name: 'sg-a-modified' },
            },
          },
          {
            address: 'aws_security_group.sg_b',
            mode: 'managed',
            type: 'aws_security_group',
            name: 'sg_b',
            provider_name: 'registry.terraform.io/hashicorp/aws',
            change: {
              actions: ['update'],
              before: { name: 'sg-b' },
              after: { name: 'sg-b-modified' },
            },
          },
        ],
        configuration: {
          root_module: {
            resources: [
              {
                address: 'aws_security_group.sg_a',
                mode: 'managed',
                type: 'aws_security_group',
                name: 'sg_a',
                depends_on: ['aws_security_group.sg_b'],
              },
              {
                address: 'aws_security_group.sg_b',
                mode: 'managed',
                type: 'aws_security_group',
                name: 'sg_b',
                depends_on: ['aws_security_group.sg_a'],
              },
            ],
          },
        },
      },
      null,
      2
    ),
  },
];
